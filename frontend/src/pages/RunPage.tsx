import { useState, useRef, useEffect } from 'react';
import { Run, RunStatus, WSMessage } from '../types';
import { api } from '../api';
import { ContextBuilder } from '../components/ContextBuilder';
import { PhaseTimeline } from '../components/PhaseTimeline';
import { OutputPanels } from '../components/OutputPanels';
import { HumanInputModal } from '../components/HumanInputModal';

type RunState = 'idle' | 'running' | 'waiting' | 'done';

export function RunPage() {
  const [state, setState] = useState<RunState>('idle');
  const [runId, setRunId] = useState<number | null>(null);
  const [currentPhase, setCurrentPhase] = useState<RunStatus>('pending');
  const [completedPhases, setCompletedPhases] = useState<RunStatus[]>([]);
  const [planOutput, setPlanOutput] = useState<any>(null);
  const [coderOutputs, setCoderOutputs] = useState<any[]>([]);
  const [testReports, setTestReports] = useState<any[]>([]);
  const [humanRequest, setHumanRequest] = useState<{ message: string; requested_by: string; input_type: string } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const phasesRef = useRef<{ current: RunStatus; completed: RunStatus[] }>({ current: 'pending', completed: [] });

  const allPhases: RunStatus[] = ['planning_draft', 'planning_review_coder', 'planning_review_tester', 'planning_finalize', 'coding', 'testing', 'evaluating'];

  const connectWS = (runId: number) => {
    const ws = new WebSocket(`ws://localhost:8000/ws/runs/${runId}`);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      const msg: WSMessage = JSON.parse(e.data);
      handleWSMessage(msg);
    };
    ws.onclose = () => { wsRef.current = null; };
    ws.onerror = () => { /* handled by onclose */ };
  };

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
        if (msg.agent === 'planner' && (msg.phase === 'planning_draft' || msg.phase === 'planning_finalize')) {
          setPlanOutput(msg.output);
        }
        if (msg.agent === 'coder' && msg.phase === 'coding') {
          setCoderOutputs(prev => [...prev, msg.output]);
        }
        if (msg.agent === 'tester' && msg.phase === 'testing') {
          setTestReports(prev => [...prev, msg.output]);
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
        break;
      case 'failed':
        setCurrentPhase('failed');
        setState('done');
        break;
    }
  };

  const onRunStart = (run: Run) => {
    setRunId(run.id);
    phasesRef.current = { current: 'pending', completed: [] };
    setCompletedPhases([]);
    setCurrentPhase('pending');
    setPlanOutput(null);
    setCoderOutputs([]);
    setTestReports([]);
    setHumanRequest(null);
    setState('running');
    connectWS(run.id);
  };

  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

  return (
    <div>
      {state === 'idle' && <ContextBuilder onRunStart={onRunStart} />}

      {(state === 'running' || state === 'waiting' || state === 'done') && (
        <div>
          <PhaseTimeline currentPhase={currentPhase} completedPhases={completedPhases} allPhases={allPhases} />
          <OutputPanels planOutput={planOutput} coderOutputs={coderOutputs} testReports={testReports} />
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
          <button onClick={() => setState('idle')} className="mt-2 px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700">Start New Run</button>
        </div>
      )}
    </div>
  );
}
