export type AgentOutput = {
  phase: string;
  agent: string;
  output: any;
  error?: string;
  timestamp?: number;
};

export function OutputPanels({ outputs }: { outputs: AgentOutput[] }) {
  // Group outputs by agent
  const plannerOutputs = outputs.filter(o => o.agent === 'planner');
  const coderOutputs = outputs.filter(o => o.agent === 'coder');
  const testerOutputs = outputs.filter(o => o.agent === 'tester');

  const renderOutputCard = (output: AgentOutput, index: number) => {
    const hasError = !!output.error;
    return (
      <div key={`${output.phase}-${index}`} className={`mb-3 p-3 rounded-lg border ${hasError ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-white'}`}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{output.phase}</span>
          {hasError && <span className="text-xs font-bold text-red-600">ERROR</span>}
        </div>
        {output.error ? (
          <p className="text-xs text-red-600">{output.error}</p>
        ) : (
          <pre className="text-xs whitespace-pre-wrap bg-gray-50 p-2 rounded">{output.output ? JSON.stringify(output.output, null, 2) : 'No output'}</pre>
        )}
      </div>
    );
  };

  return (
    <div className="grid grid-cols-3 gap-4 mt-4">
      <div className="border rounded-lg p-3 max-h-[500px] overflow-y-auto">
        <h4 className="font-semibold text-sm mb-3 text-blue-700 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-blue-500"></span>
          PLANNER
        </h4>
        {plannerOutputs.length === 0 ? (
          <p className="text-xs text-gray-400 italic">Waiting for planner...</p>
        ) : (
          plannerOutputs.map((o, i) => renderOutputCard(o, i))
        )}
      </div>

      <div className="border rounded-lg p-3 max-h-[500px] overflow-y-auto">
        <h4 className="font-semibold text-sm mb-3 text-green-700 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-500"></span>
          CODER
        </h4>
        {coderOutputs.length === 0 ? (
          <p className="text-xs text-gray-400 italic">Waiting for coder...</p>
        ) : (
          coderOutputs.map((o, i) => renderOutputCard(o, i))
        )}
      </div>

      <div className="border rounded-lg p-3 max-h-[500px] overflow-y-auto">
        <h4 className="font-semibold text-sm mb-3 text-orange-700 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-orange-500"></span>
          TESTER
        </h4>
        {testerOutputs.length === 0 ? (
          <p className="text-xs text-gray-400 italic">Waiting for tester...</p>
        ) : (
          testerOutputs.map((o, i) => renderOutputCard(o, i))
        )}
      </div>
    </div>
  );
}
