import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { Run, RunStatus, RunStep, HumanInputRequest } from '../types';

type RunState = 'idle' | 'running' | 'waiting' | 'done';

interface RunContextValue {
  // Core state
  runState: RunState;
  runId: number | null;
  currentPhase: RunStatus;
  completedPhases: RunStatus[];
  errors: { phase: string; message: string }[];
  steps: RunStep[];
  activeStep: Partial<RunStep> & { model?: string };
  streamBuffer: string;
  humanRequest: HumanInputRequest | null;

  // Actions
  startRun: (run: Run) => void;
  stopRun: () => void;
  setRunState: (state: RunState) => void;
  setCurrentPhase: (phase: RunStatus) => void;
  setCompletedPhases: (phases: RunStatus[]) => void;
  setErrors: (errs: { phase: string; message: string }[]) => void;
  setSteps: (steps: RunStep[]) => void;
  setActiveStep: (step: Partial<RunStep> & { model?: string }) => void;
  setStreamBuffer: (buffer: string) => void;
  setHumanRequest: (req: HumanInputRequest | null) => void;
  appendStream: (text: string) => void;
  appendError: (phase: string, message: string) => void;
  addStep: (step: RunStep) => void;
}

const RunContext = createContext<RunContextValue | undefined>(undefined);

export function RunProvider({ children }: { children: ReactNode }) {
  const [runState, setRunState] = useState<RunState>('idle');
  const [runId, setRunId] = useState<number | null>(null);
  const [currentPhase, setCurrentPhase] = useState<RunStatus>('pending');
  const [completedPhases, setCompletedPhases] = useState<RunStatus[]>([]);
  const [errors, setErrors] = useState<{ phase: string; message: string }[]>([]);

  // New state for the restructured layout
  const [steps, setSteps] = useState<RunStep[]>([]);
  const [activeStep, setActiveStep] = useState<Partial<RunStep> & { model?: string }>({});
  const [streamBuffer, setStreamBuffer] = useState('');
  const [humanRequest, setHumanRequest] = useState<HumanInputRequest | null>(null);

  const startRun = useCallback((run: Run) => {
    setRunId(run.id);
    setCurrentPhase('pending');
    setCompletedPhases([]);
    setErrors([]);
    setSteps([]);
    setActiveStep({});
    setStreamBuffer('');
    setHumanRequest(null);
    setRunState('running');
  }, []);

  const stopRun = useCallback(() => {
    setRunState('idle');
    setRunId(null);
    setCurrentPhase('pending');
    setCompletedPhases([]);
    setSteps([]);
    setActiveStep({});
    setStreamBuffer('');
    setHumanRequest(null);
  }, []);

  const appendStream = useCallback((text: string) => {
    setStreamBuffer(prev => prev + text);
  }, []);

  const appendError = useCallback((phase: string, message: string) => {
    setErrors(prev => [...prev, { phase, message }]);
  }, []);

  const addStep = useCallback((step: RunStep) => {
    setSteps(prev => [...prev, step]);
  }, []);

  return (
    <RunContext.Provider
      value={{
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
        setErrors,
        setSteps,
        setActiveStep,
        setStreamBuffer,
        setHumanRequest,
        appendStream,
        appendError,
        addStep,
      }}
    >
      {children}
    </RunContext.Provider>
  );
}

export function useRunContext() {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error('useRunContext must be used within RunProvider');
  return ctx;
}
