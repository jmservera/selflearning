import { NavLink } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, Network, ChevronLeft } from 'lucide-react';

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
}

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/knowledge', icon: Network, label: 'Knowledge Explorer' },
  { path: '/chat', icon: MessageSquare, label: 'Chat' },
];

export function Sidebar({ isOpen, onToggle }: SidebarProps) {
  return (
    <aside
      className={`bg-slate-900 border-r border-slate-800 transition-all duration-300 ${
        isOpen ? 'w-64' : 'w-16'
      }`}
    >
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between p-4 border-b border-slate-800">
          {isOpen && (
            <h1 className="text-lg font-semibold text-blue-400">Self-Learning</h1>
          )}
          <button
            onClick={onToggle}
            className="p-2 rounded-lg hover:bg-slate-800 transition-colors"
            aria-label={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          >
            <ChevronLeft
              className={`w-5 h-5 transition-transform ${!isOpen ? 'rotate-180' : ''}`}
            />
          </button>
        </div>

        <nav className="flex-1 p-2">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-3 rounded-lg mb-1 transition-colors ${
                  isActive
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                }`
              }
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              {isOpen && <span className="font-medium">{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-emerald-500 flex-shrink-0" />
            {isOpen && (
              <div className="text-sm">
                <div className="font-medium">Control UI</div>
                <div className="text-slate-500">v0.0.1</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}
