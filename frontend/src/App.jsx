import { useEffect } from 'react';
import { Toaster } from 'sonner';
import { AnimatePresence, motion } from 'framer-motion';
import { useStore } from './store.js';
import AuthScreen from './components/AuthScreen.jsx';
import ChatList from './components/ChatList.jsx';
import ChatView from './components/ChatView.jsx';

export default function App() {
  const booting = useStore((s) => s.booting);
  const me = useStore((s) => s.me);
  const activeId = useStore((s) => s.activeId);
  const boot = useStore((s) => s.boot);
  const removeExpired = useStore((s) => s.removeExpired);

  useEffect(() => {
    boot();
  }, [boot]);

  // Messages vanish from the view when their expires_at passes.
  useEffect(() => {
    const t = setInterval(() => removeExpired(), 15_000);
    return () => clearInterval(t);
  }, [removeExpired]);

  let content;
  if (booting) content = <div className="grid h-full place-items-center text-gray-500">Loading…</div>;
  else if (!me) content = <AuthScreen />;
  else
    content = (
      <div className="flex h-full">
        <div className={`${activeId ? 'hidden md:flex' : 'flex'} w-full flex-col border-r border-[#1a1a1a] md:w-96 bg-[#0a0a0a]`}>
          <ChatList />
        </div>
        <div className="relative min-w-0 flex-1 bg-[#000000]">
          <AnimatePresence mode="wait">
            {activeId ? (
              <motion.div
                key={activeId}
                className="absolute inset-0"
                initial={{ x: 40, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: 40, opacity: 0 }}
                transition={{ duration: 0.18 }}
              >
                <ChatView />
              </motion.div>
            ) : (
              <div className="hidden h-full place-items-center text-gray-500 md:grid">
                Select a chat. Messages self-delete after their timer.
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    );

  return (
    <div className="h-full bg-[#000000]">
      {content}
      <Toaster theme="dark" position="top-center" richColors />
    </div>
  );
}
