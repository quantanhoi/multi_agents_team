import { useRef, useEffect, useCallback } from 'react';
import { RunStatus, RunStep, Run, WSMessage } from '../types';
import { api } from '../api';
import { useRunContext } from '../context/RunContext';
import { ContextBuilder } from '../components/ContextBuilder';
import { PhaseTimeline } from '../components/PhaseTimeline';
import ActiveStepPanel from '../components/ActiveStepPanel';
import HistoryPanel from '../components/HistoryPanel';
import HumanInputPanel from '../components/HumanInputPanel';

export function RunPage() {
  const {
    runState,
    runId,
    currentPhase,
    completedPhases,
    errors,
    steps,
    activeStep,
    streamBuffer,
    humanRequest,
    startRun,
    stopRun,
    setRunState,
    setCurrentPhase,
    setCompletedPhases,
    setSteps,
    setActiveStep,
    setStreamBuffer,
    setHumanRequest,
    appendStream,
    appendError,
    addStep,
  } = useRunContext();

  // Refs to keep latest values accessible in WS handlers without stale closures
  const stepsRef = useRef<RunStep[]>([]);
  const activeStepRef = useRef<Partial<RunStep> & { model?: string }>({});
  const streamBufferRef = useRef('');
  const phasesRef = useRef<{ current: RunStatus; completed: RunStatus[] }>({ current: 'pending', completed: [] });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);

  const allPhases: RunStatus[] = ['planning_draft', 'planning_review_coder', 'planning_review_tester', 'planning_finalize', 'coding', 'testing', 'evaluating'];

  const clearReconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  // Sync display from refs when state changes
  const syncDisplay = useCallback(() => {
    setSteps([...stepsRef.current]);
    setActiveStep({ ...activeStepRef.current });
    setStreamBuffer(streamBufferRef.current);
  }, [setSteps, setActiveStep, setStreamBuffer]);

  const finalizeActiveStep = useCallback(() => {
    if (activeStepRef.current.step_number !== undefined) {
      stepsRef.current.push(activeStepRef.current as RunStep);
      addStep(activeStepRef.current as RunStep);
    }
    activeStepRef.current = {};
    streamBufferRef.current = '';
    syncDisplay();
  }, [addStep, syncDisplay]);

  // ── WebSocket connection ─────────────────────────────────────────
  const connectWS = useCallback((targetRunId: number) => {
    clearReconnect();
    const apiBase = (import.meta as any).env?.VITE_API_BASE_URL || '';
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = apiBase ? new URL(apiBase).host : window.location.host;
    const wsUrl = `${wsProto}//${wsHost}/ws/runs/${targetRunId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttemptRef.current = 0;
    };

    ws.onmessage = (e) => {
      const msg: WSMessage = JSON.parse(e.data);
      handleWSMessage(msg);
    };

    ws.onclose = () => {
      wsRef.current = null;
      // Auto-reconnect with exponential backoff (max 30s) unless run is done/failed
      if (runState !== 'done' && targetRunId) {
        const delay = Math.min(1000 * 2 ** reconnectAttemptRef.current, 30000);
        reconnectAttemptRef.current += 1;
        reconnectTimeoutRef.current = setTimeout(() => connectWS(targetRunId), delay);
      }
    };

    ws.onerror = () => {
      // onclose handles reconnection
    };
  }, [clearReconnect, runState]);

  // ── Fetch existing run state on mount ───────────────────────────
  useEffect(() => {
    // If we return to this page and there's an active run, reconnect WS
    if (runId && (runState === 'running' || runState === 'waiting')) {
      // Re-establish websocket
      connectWS(runId);
      // Optionally re-fetch steps from backend to sync history
      api.runs.getSteps(runId).then((backendSteps) => {
        if (backendSteps && backendSteps.length > stepsRef.current.length) {
          stepsRef.current = backendSteps;
          setSteps(backendSteps);
        }
      }).catch(() => {
        // Ignore fetch errors
      });
    }

    return () => {
      // DO NOT close WS or clear reconnect on unmount — we want to stay connected across navigation
      // Only cleanup when the component is truly unmounting (e.g. app close) is handled below
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run once on mount

  // Cleanup on app unload
  useEffect(() => {
    const handleBeforeUnload = () => {
      clearReconnect();
      wsRef.current?.close();
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [clearReconnect]);

  const handleWSMessage = useCallback((msg: WSMessage) => {
    const p = phasesRef.current;
    switch (msg.type) {
      case 'phase_change':
        if (msg.phase && msg.phase !== 'waiting_for_human') {
          if (p.current && p.current !== 'pending' && !p.completed.includes(p.current)) {
            p.completed.push(p.current);
          }
          p.current = msg.phase as RunStatus;
          setCurrentPhase(msg.phase as RunStatus);
          setCompletedPhases([...p.completed]);

          // Finalize previous active step before starting new one
          finalizeActiveStep();

          activeStepRef.current = {
            step_number: msg.step_number,
            agent: msg.role || msg.agent,
            step_type: msg.phase,
            model: msg.model,
            output: {},
            files_changed: [],
            created_at: new Date().toISOString(),
          };
          streamBufferRef.current = '';
          syncDisplay();
        }
        break;
      case 'agent_output':
        if (msg.agent || msg.phase) {
          const text = typeof msg.output === 'string' ? msg.output : JSON.stringify(msg.output);
          streamBufferRef.current += text;
          appendStream(text);
          activeStepRef.current = {
            ...activeStepRef.current,
            agent: msg.agent || activeStepRef.current.agent,
            step_type: msg.phase || activeStepRef.current.step_type,
            output: {
              ...activeStepRef.current.output,
              raw_output: (activeStepRef.current.output?.raw_output || '') + text,
            },
          };
          syncDisplay();
        }
        break;
      case 'phase_error':
        if (msg.phase && msg.message) {
          appendError(msg.phase, msg.message);
        }
        break;
      case 'human_input_required':
        setRunState('waiting');
        setHumanRequest({
          message: msg.message!,
          requested_by: msg.requested_by!,
          input_type: (msg.input_type as any) || 'text',
        });
        break;
      case 'done':
        if (p.current && !p.completed.includes(p.current)) p.completed.push(p.current);
        setCompletedPhases([...p.completed]);
        setCurrentPhase('done');
        setRunState('done');
        finalizeActiveStep();
        clearReconnect();
        break;
      case 'failed':
        setCurrentPhase('failed');
        setRunState('done');
        finalizeActiveStep();
        clearReconnect();
        break;
    }
  }, [setCurrentPhase, setCompletedPhases, setRunState, setHumanRequest, appendError, appendStream, finalizeActiveStep, clearReconnect, syncDisplay]);

  const sendOverride = useCallback((text: string) => {
    if (!runId || !text.trim()) return;
    // eslint-disable-next-line no-console
    console.log('Override for run', runId, ':', text);
    // TODO: send to backend once override endpoint is available
  }, [runId]);

  const onRunStart = useCallback((run: Run) => {
    // Reset phases ref
    phasesRef.current = { current: 'pending', completed: [] };
    stepsRef.current = [];
    activeStepRef.current = {};
    streamBufferRef.current = '';

    startRun(run);
    connectWS(run.id);
  }, [startRun, connectWS]);

  return (
    <div>
      {runState === 'idle' && <ContextBuilder onRunStart={onRunStart} />}

      {(runState === 'running' || runState === 'waiting' || runState === 'done') && (
        <div className="space-y-4">
          <PhaseTimeline currentPhase={currentPhase} completedPhases={completedPhases} allPhases={allPhases} />

          {errors.length > 0 && (
            <div className="p-3 bg-red-50 rounded-lg border border-red-200">
              <h4 className="text-sm font-semibold text-red-700 mb-1">Phase Errors</h4>
              {errors.map((err, i) => (
                <p key={i} className="text-xs text-red-600">{err.phase}: {err.message}</p>
              ))}
            </div>
          )}

          <ActiveStepPanel step={activeStep} stream={streamBuffer} onOverride={sendOverride} />

          <HistoryPanel steps={steps} />

          <HumanInputPanel
            request={humanRequest ? { message: humanRequest.message, input_type: humanRequest.input_type } : null}
            onSubmit={(text: string) => {
              if (!runId) return;
              api.runs.resume(runId, { response_text: text, uploaded_files: [] });
              setHumanRequest(null);
              setRunState('running');
            }}
          />
        </div>
      )}

      {runState === 'done' && (
        <div className="mt-4 p-4 bg-green-50 rounded-lg">
          <p className="font-semibold text-green-800">
            {currentPhase === 'done' ? 'Run completed successfully!' : 'Run failed.'}
          </p>
          <button
            onClick={() => {
              clearReconnect();
              stopRun();
            }}
            className="mt-2 px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
          >
            Start New Run
          </button>
        </div>
      )}
    </div>
  );
}
