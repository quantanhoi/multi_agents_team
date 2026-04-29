import { useState, useRef, useEffect, useCallback } from 'react';
import { Run, RunStatus, RunStep, HumanInputRequest, WSMessage } from '../types';
import { api } from '../api';
import { ContextBuilder } from '../components/ContextBuilder';
import { PhaseTimeline } from '../components/PhaseTimeline';
import ActiveStepPanel from '../components/ActiveStepPanel';
import HistoryPanel from '../components/HistoryPanel';
import HumanInputPanel from '../components/HumanInputPanel';

type RunState = 'idle' | 'running' | 'waiting' | 'done';

export function RunPage() {
  const [state, setState] = useState<RunState>('idle');
  const [runId, setRunId] = useState<number | null>(null);
  const [currentPhase, setCurrentPhase] = useState<RunStatus>('pending');
  const [completedPhases, setCompletedPhases] = useState<RunStatus[]>([]);
  const [errors, setErrors] = useState<{phase: string; message: string}[]>([]);

  // New state for the restructured layout
  const [steps, setSteps] = useState<RunStep[]>([]);
  const [activeStep, setActiveStep] = useState<Partial<RunStep> & { model?: string }>({});
  const [streamBuffer, setStreamBuffer] = useState('');
  const [humanRequest, setHumanRequest] = useState<HumanInputRequest | null>(null);

  // Refs to keep latest values accessible in WS handlers without stale closures
  const stepsRef = useRef<RunStep[]>([]);
  const activeStepRef = useRef<Partial<RunStep> & { model?: string }>({});
  const streamBufferRef = useRef('');

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const phasesRef = useRef<{ current: RunStatus; completed: RunStatus[] }>({ current: 'pending', completed: [] });

  const allPhases: RunStatus[] = ['planning_draft', 'planning_review_coder', 'planning_review_tester', 'planning_finalize', 'coding', 'testing', 'evaluating'];

  const clearReconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const syncDisplay = () => {
    setSteps([...stepsRef.current]);
    setActiveStep({ ...activeStepRef.current });
    setStreamBuffer(streamBufferRef.current);
  };

  const finalizeActiveStep = () => {
    if (activeStepRef.current.step_number !== undefined) {
      stepsRef.current.push(activeStepRef.current as RunStep);
    }
    activeStepRef.current = {};
    streamBufferRef.current = '';
    syncDisplay();
  };

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
      if (state !== 'done' && targetRunId) {
        const delay = Math.min(1000 * 2 ** reconnectAttemptRef.current, 30000);
        reconnectAttemptRef.current += 1;
        reconnectTimeoutRef.current = setTimeout(() => connectWS(targetRunId), delay);
      }
    };

    ws.onerror = () => {
      // onclose handles reconnection
    };
  }, [clearReconnect, state]);

  const handleWSMessage = (msg: WSMessage) => {
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
          setErrors(prev => [...prev, { phase: msg.phase!, message: msg.message! }]);
        }
        break;
      case 'human_input_required':
        setState('waiting');
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
        setState('done');
        finalizeActiveStep();
        clearReconnect();
        break;
      case 'failed':
        setCurrentPhase('failed');
        setState('done');
        finalizeActiveStep();
        clearReconnect();
        break;
    }
  };

  const sendOverride = useCallback((text: string) => {
    if (!runId || !text.trim()) return;
    // eslint-disable-next-line no-console
    console.log('Override for run', runId, ':', text);
    // TODO: send to backend once override endpoint is available
  }, [runId]);

  const onRunStart = (run: Run) => {
    setRunId(run.id);
    phasesRef.current = { current: 'pending', completed: [] };
    setCompletedPhases([]);
    setCurrentPhase('pending');
    stepsRef.current = [];
    activeStepRef.current = {};
    streamBufferRef.current = '';
    setSteps([]);
    setActiveStep({});
    setStreamBuffer('');
    setErrors([]);
    setHumanRequest(null);
    setState('running');
    connectWS(run.id);
  };

  useEffect(() => {
    return () => {
      clearReconnect();
      wsRef.current?.close();
    };
  }, [clearReconnect]);

  return (
    <div>
      {state === 'idle' && <ContextBuilder onRunStart={onRunStart} />}

      {(state === 'running' || state === 'waiting' || state === 'done') && (
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
            onSubmit={(text) => {
              if (!runId) return;
              api.runs.resume(runId, { response_text: text, uploaded_files: [] });
              setHumanRequest(null);
              setState('running');
            }}
          />
        </div>
      )}

      {state === 'done' && (
        <div className="mt-4 p-4 bg-green-50 rounded-lg">
          <p className="font-semibold text-green-800">
            {currentPhase === 'done' ? 'Run completed successfully!' : 'Run failed.'}
          </p>
          <button onClick={() => {
            clearReconnect();
            setState('idle');
            setRunId(null);
          }} className="mt-2 px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700">Start New Run</button>
        </div>
      )}
    </div>
  );
}
