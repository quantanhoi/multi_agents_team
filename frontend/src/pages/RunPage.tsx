import { useState, useRef, useEffect, useCallback } from 'react';
import { Run, RunStatus, WSMessage } from '../types';
import { api } from '../api';
import { ContextBuilder } from '../components/ContextBuilder';
import { PhaseTimeline } from '../components/PhaseTimeline';
import { OutputPanels, AgentOutput } from '../components/OutputPanels';
import { HumanInputModal } from '../components/HumanInputModal';

type RunState = 'idle' | 'running' | 'waiting' | 'done';

export function RunPage() {
  const [state, setState] = useState<RunState>('idle');
  const [runId, setRunId] = useState<number | null>(null);
  const [currentPhase, setCurrentPhase] = useState<RunStatus>('pending');
  const [completedPhases, setCompletedPhases] = useState<RunStatus[]>([]);
  const [agentOutputs, setAgentOutputs] = useState<AgentOutput[]>([]);
  const [errors, setErrors] = useState<{phase: string; message: string}[]>([]);
  const [humanRequest, setHumanRequest] = useState<{ message: string; requested_by: string; input_type: string } | null>(null);
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
        }
        break;
      case 'agent_output':
        if (msg.phase && msg.agent) {
          setAgentOutputs(prev => [...prev, {
            phase: msg.phase!,
            agent: msg.agent!,
            output: msg.output,
            error: msg.error,
            timestamp: Date.now(),
          }]);
        }
        break;
      case 'phase_error':
        if (msg.phase && msg.message) {
          setErrors(prev => [...prev, { phase: msg.phase!, message: msg.message! }]);
        }
        break;
      case 'human_input_required':
        setState('waiting');
        setHumanRequest({ message: msg.message!, requested_by: msg.requested_by!, input_type: msg.input_type || 'text' });
        break;
      case 'done':
        if (p.current && !p.completed.includes(p.current)) p.completed.push(p.current);
        setCompletedPhases([...p.completed]);
        setCurrentPhase('done');
        setState('done');
        clearReconnect();
        break;
      case 'failed':
        setCurrentPhase('failed');
        setState('done');
        clearReconnect();
        break;
    }
  };

  const onRunStart = (run: Run) => {
    setRunId(run.id);
    phasesRef.current = { current: 'pending', completed: [] };
    setCompletedPhases([]);
    setCurrentPhase('pending');
    setAgentOutputs([]);
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
        <div>
          <PhaseTimeline currentPhase={currentPhase} completedPhases={completedPhases} allPhases={allPhases} />

          {errors.length > 0 && (
            <div className="mb-4 p-3 bg-red-50 rounded-lg border border-red-200">
              <h4 className="text-sm font-semibold text-red-700 mb-1">Phase Errors</h4>
              {errors.map((err, i) => (
                <p key={i} className="text-xs text-red-600">{err.phase}: {err.message}</p>
              ))}
            </div>
          )}

          <OutputPanels outputs={agentOutputs} />
        </div>
      )}

      {state === 'waiting' && humanRequest && (
        <HumanInputModal
          message={humanRequest.message}
          requestedBy={humanRequest.requested_by}
          inputType={humanRequest.input_type}
          onSubmit={async (text, files) => {
            if (!runId) return;
            await api.runs.resume(runId, { response_text: text, uploaded_files: files });
            setHumanRequest(null);
            setState('running');
          }}
        />
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
