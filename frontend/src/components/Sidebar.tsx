import { NavLink } from 'react-router-dom';

export function Sidebar() {
  const links = [
    { to: '/', label: 'Run' },
    { to: '/agents', label: 'Agents' },
    { to: '/jobs', label: 'Jobs' },
    { to: '/history', label: 'History' },
    { to: '/settings', label: 'Settings' },
  ];
  return (
    <nav className="w-48 bg-gray-900 text-white p-4 flex flex-col gap-2">
      <h1 className="text-lg font-bold mb-4">Multi-Agent Studio</h1>
      {links.map(l => (
        <NavLink key={l.to} to={l.to} className={({isActive}) => `px-3 py-2 rounded ${isActive ? 'bg-blue-600' : 'hover:bg-gray-700'}`}>
          {l.label}
        </NavLink>
      ))}
    </nav>
  );
}
