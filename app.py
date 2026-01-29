import React, { useState, useEffect, useRef } from 'react';
import { 
  Send, 
  User, 
  Lock, 
  GraduationCap, 
  BookOpen, 
  Mic, 
  Volume2, 
  LogOut, 
  BrainCircuit, 
  ChevronLeft,
  CheckCircle2,
  Sparkles
} from 'lucide-react';
import confetti from 'canvas-confetti';
import { motion, AnimatePresence } from 'framer-motion';

// --- أنواع البيانات ---
type Message = {
  id: string;
  role: 'assistant' | 'user';
  content: string;
  timestamp: Date;
};

function App() {
  // --- حالة المستخدم ---
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userData, setUserData] = useState({
    name: '',
    grade: '',
    stage: 'الثانوية',
    code: ''
  });

  // --- حالة الدردشة ---
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // --- تمرير الدردشة للأسفل ---
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // --- نظام تسجيل الدخول ---
  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (userData.name && (userData.code === '1234' || userData.code === 'ADMIN')) {
      setIsLoggedIn(true);
      setMessages([{
        id: '1',
        role: 'assistant',
        content: `مرحباً بك يا ${userData.name}! أنا معلمك الافتراضي لمادة العلوم. كيف يمكنني مساعدتك اليوم؟ يمكنك سؤالي عن أي شيء أو كتابة "ابدأ اختبار" لنختبر معلوماتك.`,
        timestamp: new Date()
      }]);
      confetti({
        particleCount: 150,
        spread: 70,
        origin: { y: 0.6 }
      });
    } else {
      alert('❌ عذراً، الكود السري غير صحيح. حاول مرة أخرى (الكود التجريبي: 1234)');
    }
  };

  // --- محاكاة رد المعلم الذكي ---
  const getAIResponse = (userInput: string) => {
    const text = userInput.toLowerCase();
    
    if (text.includes('اختبار') || text.includes('سؤال')) {
      return "حسناً! لنبدأ اختباراً سريعاً. ما هو الغاز الذي تتنفسه الكائنات الحية لتعيش؟ (الأكسجين - ثاني أكسيد الكربون - النيتروجين)";
    }
    
    if (text.includes('الأكسجين') || text.includes('أكسجين')) {
      confetti({ particleCount: 100, spread: 50 });
      return "إجابة ممتازة وصحيحة! الأكسجين هو غاز الحياة. هل تود سؤالاً آخر؟";
    }

    if (text.includes('شكرا') || text.includes('شكراً')) {
      return "العفو يا بطل! أنا هنا دائماً لمساعدتك في رحلتك العلمية.";
    }

    return "هذا سؤال رائع! في عالم العلوم، كل شيء يبدأ بالتساؤل. هل يمكنك توضيح سؤالك أكثر لأتمكن من شرحه لك بشكل مفصل؟";
  };

  const handleSendMessage = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim()) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);

    // محاكاة تفكير المعلم
    setTimeout(() => {
      const aiMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: getAIResponse(input),
        timestamp: new Date()
      };
      setMessages(prev => [...prev, aiMsg]);
      setIsTyping(false);
    }, 1500);
  };

  // --- ميزة النطق الصوتي ---
  const speak = (text: string) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ar-SA';
    window.speechSynthesis.speak(utterance);
  };

  if (!isLoggedIn) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 bg-gradient-to-br from-slate-900 via-[#004e92] to-slate-900">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-md p-8 glass-card rounded-3xl shadow-2xl"
        >
          <div className="text-center mb-8">
            <div className="bg-blue-600 w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg rotate-3">
              <GraduationCap size={40} className="text-white" />
            </div>
            <h1 className="text-3xl font-bold text-slate-800">الأستاذ السيد البدوي</h1>
            <p className="text-slate-500 mt-2">منصة المعلم العلمي الذكية</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">الاسم الثلاثي</label>
              <div className="relative">
                <User className="absolute right-3 top-3 text-slate-400" size={20} />
                <input 
                  required
                  type="text"
                  placeholder="أدخل اسمك هنا"
                  className="w-full pr-11 pl-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                  value={userData.name}
                  onChange={e => setUserData({...userData, name: e.target.value})}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">المرحلة</label>
                <select 
                  className="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-blue-500"
                  value={userData.stage}
                  onChange={e => setUserData({...userData, stage: e.target.value})}
                >
                  <option>الابتدائية</option>
                  <option>الإعدادية</option>
                  <option>الثانوية</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">الصف</label>
                <select 
                  className="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-blue-500"
                  value={userData.grade}
                  onChange={e => setUserData({...userData, grade: e.target.value})}
                >
                  <option>الأول</option>
                  <option>الثاني</option>
                  <option>الثالث</option>
                  <option>الرابع</option>
                  <option>الخامس</option>
                  <option>السادس</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">الكود السري</label>
              <div className="relative">
                <Lock className="absolute right-3 top-3 text-slate-400" size={20} />
                <input 
                  required
                  type="password"
                  placeholder="أدخل الكود الخاص بك"
                  className="w-full pr-11 pl-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                  value={userData.code}
                  onChange={e => setUserData({...userData, code: e.target.value})}
                />
              </div>
            </div>

            <button 
              type="submit"
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-xl shadow-lg hover:shadow-blue-500/30 transition-all flex items-center justify-center gap-2 group"
            >
              <span>بدأ رحلة التعلم</span>
              <ChevronLeft size={20} className="group-hover:-translate-x-1 transition-transform" />
            </button>
          </form>

          <p className="text-center text-slate-400 text-sm mt-6">
            جميع الحقوق محفوظة للأستاذ السيد البدوي © 2024
          </p>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-[#f8fafc]">
      {/* القائمة الجانبية */}
      <aside className="w-80 bg-slate-900 text-white hidden md:flex flex-col p-6 shadow-2xl">
        <div className="flex items-center gap-3 mb-10">
          <div className="bg-blue-600 p-2 rounded-lg">
            <BrainCircuit size={28} />
          </div>
          <div>
            <h2 className="font-bold text-lg leading-tight">المعلم العلمي</h2>
            <p className="text-slate-400 text-xs text-right">الأستاذ السيد البدوي</p>
          </div>
        </div>

        <nav className="flex-1 space-y-2">
          <div className="p-4 bg-slate-800/50 rounded-2xl border border-slate-700 mb-6">
            <p className="text-xs text-slate-400 mb-1 text-right">الطالب الحالي:</p>
            <p className="font-bold text-blue-400">{userData.name}</p>
            <p className="text-xs text-slate-300 mt-1">{userData.stage} - الصف {userData.grade}</p>
          </div>

          <button 
            onClick={() => { setInput('ابدأ اختبار'); handleSendMessage(); }}
            className="w-full flex items-center gap-3 p-4 rounded-xl hover:bg-slate-800 transition-colors text-right"
          >
            <Sparkles className="text-yellow-400" size={20} />
            <span>ابدأ اختبار سريع</span>
          </button>

          <button className="w-full flex items-center gap-3 p-4 rounded-xl hover:bg-slate-800 transition-colors text-right">
            <BookOpen className="text-blue-400" size={20} />
            <span>المكتبة الرقمية</span>
          </button>
        </nav>

        <button 
          onClick={() => setIsLoggedIn(false)}
          className="flex items-center gap-3 p-4 rounded-xl hover:bg-red-500/10 text-red-400 transition-colors mt-auto border border-red-500/20"
        >
          <LogOut size={20} />
          <span>تسجيل الخروج</span>
        </button>
      </aside>

      {/* منطقة الدردشة الرئيسية */}
      <main className="flex-1 flex flex-col relative overflow-hidden">
        {/* الهيدر العلوي للجوال */}
        <header className="md:hidden p-4 bg-white border-b flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-2">
            <div className="bg-blue-600 p-1.5 rounded-lg text-white">
              <BrainCircuit size={20} />
            </div>
            <span className="font-bold text-slate-800">المعلم العلمي</span>
          </div>
          <button onClick={() => setIsLoggedIn(false)} className="text-slate-400">
            <LogOut size={20} />
          </button>
        </header>

        {/* الرسائل */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6">
          <AnimatePresence initial={false}>
            {messages.map((msg) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                className={`flex ${msg.role === 'user' ? 'justify-start' : 'justify-end'} gap-3`}
              >
                <div className={`max-w-[85%] md:max-w-[70%] p-4 shadow-sm relative group ${
                  msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'
                }`}>
                  <p className="leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                  <div className="flex items-center justify-between mt-3 opacity-60 text-[10px]">
                    <span>{msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    {msg.role === 'assistant' && (
                      <button 
                        onClick={() => speak(msg.content)}
                        className="p-1 hover:bg-slate-100 rounded-full transition-colors text-blue-600"
                        title="استمع للشرح"
                      >
                        <Volume2 size={14} />
                      </button>
                    )}
                  </div>
                  {msg.role === 'assistant' && (
                    <div className="absolute -right-12 top-0 bg-blue-100 text-blue-600 p-2 rounded-full hidden md:block">
                      <CheckCircle2 size={16} />
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {isTyping && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-end">
              <div className="chat-bubble-ai p-4 flex gap-1 items-center">
                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
              </div>
            </motion.div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* صندوق الإدخال */}
        <div className="p-4 md:p-8 bg-gradient-to-t from-[#f8fafc] via-[#f8fafc] to-transparent">
          <form 
            onSubmit={handleSendMessage}
            className="max-w-4xl mx-auto relative flex items-center gap-2"
          >
            <div className="relative flex-1">
              <input 
                type="text"
                placeholder="اسأل معلمك الافتراضي عن أي شيء في العلوم..."
                className="w-full p-4 md:p-5 pr-14 rounded-2xl border border-slate-200 shadow-xl focus:ring-4 focus:ring-blue-500/10 focus:border-blue-500 outline-none transition-all text-slate-700"
                value={input}
                onChange={e => setInput(e.target.value)}
              />
              <button 
                type="button"
                className="absolute right-4 top-1/2 -translate-y-1/2 p-2 text-slate-400 hover:text-blue-600 transition-colors"
              >
                <Mic size={24} />
              </button>
            </div>
            <button 
              type="submit"
              disabled={!input.trim()}
              className="bg-blue-600 text-white p-4 md:p-5 rounded-2xl shadow-xl hover:bg-blue-700 disabled:opacity-50 disabled:hover:bg-blue-600 transition-all active:scale-95"
            >
              <Send size={24} className="rotate-180" />
            </button>
          </form>
          <p className="text-center text-[10px] text-slate-400 mt-4">
            نحن هنا لتبسيط العلوم وجعل التعلم ممتعاً. بالتوفيق يا بطل!
          </p>
        </div>
      </main>
    </div>
  );
}

export default App;
