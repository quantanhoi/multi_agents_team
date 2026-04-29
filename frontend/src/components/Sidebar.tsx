import { NavLink } from 'react-router-dom';
import { useRunContext } from '../context/RunContext';

export function Sidebar() {
  const { runState, currentPhase } = useRunContext();

  const links = [
    { to: '/', label: 'Run' },
    { to: '/agents', label: 'Agents' },
    { to: '/jobs', label: 'Jobs' },
    { to: '/history', label: 'History' },
    { to: '/settings', label: 'Settings' },
  ];

  const isRunActive = runState === 'running' || runState === 'waiting';

  return (
    <nav className="w-48 bg-gray-900 text-white p-4 flex flex-col gap-2">
      <h1 className="text-lg font-bold mb-4">Multi-Agent Studio</h1>
      {links.map(l => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) =>
            `px-3 py-2 rounded flex items-center justify-between ${
              isActive ? 'bg-blue-600' : 'hover:bg-gray-700'
            }`
          }
        >
          <span>{l.label}</span>
          {l.to === '/' && isRunActive && (
            <span className="ml-2 w-2 h-2 bg-green-400 rounded-full animate-pulse" title={`Run active: ${currentPhase}`}></span>
          )}
        </NavLink>
      ))}
      {isRunActive && (
        <div className="mt-4 px-3 py-2 bg-gray-800 rounded text-xs text-green-400">
          <strong>Run active</strong>
          <br />
          Phase: {currentPhase}
        </div>
      )}
    </nav>
  );
}
