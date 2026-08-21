import { Activity, Server, Zap, Shield, ChevronRight } from 'lucide-react';
import { motion } from 'framer-motion';

const MOCK_PROVIDERS = [
  { id: '1', name: 'codex/gpt-5.6-sol', status: 'active', latency: '45ms', load: 85 },
  { id: '2', name: 'ainative/claude-sonnet-4-5', status: 'active', latency: '120ms', load: 62 },
  { id: '3', name: 'ainative/deepseek-r1', status: 'active', latency: '85ms', load: 45 },
  { id: '4', name: 'kimi-coding/default', status: 'standby', latency: '-', load: 0 },
  { id: '5', name: 'nvidia/nemotron-3', status: 'active', latency: '210ms', load: 92 },
];

function App() {

  return (
    <div className="min-h-screen p-6 font-sans">
      <nav className="glass-panel rounded-2xl p-4 mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-accent-glow/20 flex items-center justify-center neon-border">
            <Activity className="text-accent-glow" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-wider text-white">OMNIROUTE</h1>
            <p className="text-xs text-accent-glow/70 uppercase tracking-widest">Master Routing Node</p>
          </div>
        </div>
        
        <div className="flex gap-4">
          <button className="px-6 py-2 rounded-lg bg-white/5 hover:bg-white/10 transition-colors text-sm font-medium">Settings</button>
          <button className="px-6 py-2 rounded-lg bg-accent-glow/10 text-accent-glow hover:bg-accent-glow/20 transition-colors text-sm font-medium border border-accent-glow/30">Connect Node</button>
        </div>
      </nav>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="glass-panel p-6 rounded-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-accent-glow/10 rounded-full blur-3xl" />
          <h3 className="text-sm text-gray-400 font-medium mb-2 uppercase tracking-wider">Active Connections</h3>
          <div className="flex items-end gap-4">
            <span className="text-5xl font-bold text-white">57</span>
            <span className="text-sm text-green-400 mb-1 flex items-center gap-1"><Zap size={14} /> 100% Uptime</span>
          </div>
        </motion.div>
        
        <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }} className="glass-panel p-6 rounded-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-accent-purple/10 rounded-full blur-3xl" />
          <h3 className="text-sm text-gray-400 font-medium mb-2 uppercase tracking-wider">Models in Fleet</h3>
          <div className="flex items-end gap-4">
            <span className="text-5xl font-bold text-white">6,108</span>
            <span className="text-sm text-accent-purple mb-1">Globally Distributed</span>
          </div>
        </motion.div>

        <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.2 }} className="glass-panel p-6 rounded-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-green-500/10 rounded-full blur-3xl" />
          <h3 className="text-sm text-gray-400 font-medium mb-2 uppercase tracking-wider">System Health</h3>
          <div className="flex items-center gap-3 mt-2">
            <div className="w-12 h-12 rounded-full border-4 border-green-500/20 flex items-center justify-center border-t-green-500 animate-spin-slow">
              <Shield className="text-green-400 animate-pulse-fast" size={20} />
            </div>
            <div>
              <p className="text-white font-semibold">SECURE</p>
              <p className="text-xs text-gray-400">Zero routing gaps detected</p>
            </div>
          </div>
        </motion.div>
      </div>

      <div className="glass-panel rounded-2xl p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Server className="text-accent-glow" /> 
            Live Provider Telemetry
          </h2>
          <div className="flex gap-2">
            <span className="w-2 h-2 rounded-full bg-accent-glow animate-pulse-fast mt-2" />
            <span className="text-sm text-accent-glow font-medium">STREAMING</span>
          </div>
        </div>

        <div className="w-full overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-white/10">
                <th className="pb-4 pt-2 px-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">Provider / Model</th>
                <th className="pb-4 pt-2 px-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">Status</th>
                <th className="pb-4 pt-2 px-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">Latency</th>
                <th className="pb-4 pt-2 px-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">Network Load</th>
                <th className="pb-4 pt-2 px-4 text-xs font-semibold text-gray-400 uppercase tracking-wider text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {MOCK_PROVIDERS.map((provider, i) => (
                <motion.tr 
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.1 }}
                  key={provider.id} 
                  className="border-b border-white/5 hover:bg-white/5 transition-colors group"
                >
                  <td className="py-4 px-4 font-medium text-white">{provider.name}</td>
                  <td className="py-4 px-4">
                    <span className={`px-3 py-1 rounded-full text-xs font-medium ${provider.status === 'active' ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-gray-500/10 text-gray-400 border border-gray-500/20'}`}>
                      {provider.status.toUpperCase()}
                    </span>
                  </td>
                  <td className="py-4 px-4 text-gray-300 font-mono text-sm">{provider.latency}</td>
                  <td className="py-4 px-4">
                    <div className="w-full bg-dark-900 rounded-full h-2 overflow-hidden border border-white/10">
                      <motion.div 
                        initial={{ width: 0 }}
                        animate={{ width: `${provider.load}%` }}
                        transition={{ duration: 1, delay: 0.5 }}
                        className={`h-full rounded-full ${provider.load > 80 ? 'bg-red-500' : provider.load > 50 ? 'bg-accent-glow' : 'bg-green-500'}`}
                      />
                    </div>
                  </td>
                  <td className="py-4 px-4 text-right">
                    <button className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors">
                      <ChevronRight size={18} />
                    </button>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default App;
