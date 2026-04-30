#!/usr/bin/env python3
"""
WintripAI — Alles-in-één starter
Start: cd /home/pwintri2/WintripAI && python3 start_wintrip.py

Dit script:
  1. Start controller/main.py op poort 8000
  2. Serveert de IDE HTML op poort 3000
  3. Opent de browser automatisch
  4. Stopt alles netjes bij Ctrl+C
"""

import subprocess, sys, os, time, signal, threading, webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler

WINTRIP_ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON  = os.path.join(WINTRIP_ROOT, ".venv", "bin", "python")
if not os.path.exists(VENV_PYTHON):
    VENV_PYTHON = sys.executable
CONTROLLER   = os.path.join(WINTRIP_ROOT, "controller")
BACKEND_PORT = 8000
IDE_PORT     = 3000
IDE_FILE     = "WintripAI_IDE.html"

backend_proc = None

# ── HTML van de IDE, inline zodat er geen los bestand nodig is ──────────────
IDE_HTML = r"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8"/>
<title>WintripAI — Waakbewustzijn</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.2/babel.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f1117;color:#e2e8f0;font-family:'Inter',system-ui,sans-serif;font-size:13px;height:100vh;overflow:hidden}
textarea{font-family:inherit}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:#2d3748;border-radius:2px}
button{cursor:pointer;font-family:inherit}
</style>
</head>
<body><div id="root"></div>
<script type="text/babel">
const B = "http://localhost:8000";
const OLLAMA_MODELS = [
  {id:"qwen2.5-coder:3b",label:"qwen2.5-coder:3b",size:"1.9 GB"},
  {id:"qwen2.5-coder:7b",label:"qwen2.5-coder:7b",size:"4.7 GB"},
  {id:"phi4:latest",label:"phi4:latest",size:"9.1 GB"},
  {id:"llama3.1:latest",label:"llama3.1:latest",size:"4.9 GB"},
  {id:"nomic-embed-text:latest",label:"nomic-embed-text",size:"274 MB"},
  {id:"gemma2:latest",label:"gemma2:latest",size:"5.4 GB"},
  {id:"gemma2:2b",label:"gemma2:2b",size:"1.6 GB"},
  {id:"qwen2.5:latest",label:"qwen2.5:latest",size:"4.7 GB"},
  {id:"phi3:latest",label:"phi3:latest",size:"2.2 GB"},
  {id:"llama3:latest",label:"llama3:latest",size:"4.7 GB"},
  {id:"gpt-oss:120b-cloud",label:"gpt-oss:120b-cloud",size:"cloud"},
];
const GROK_MODELS = [
  {id:"grok-3",label:"grok-3",size:"cloud"},
  {id:"grok-3-mini",label:"grok-3-mini",size:"cloud"},
  {id:"grok-2-vision",label:"grok-2-vision",size:"cloud"},
];
const PROVIDERS = [
  {id:"ollama",label:"Ollama",sub:"Local",color:"#10B981"},
  {id:"grok",label:"Grok",sub:"API",color:"#8B5CF6"},
  {id:"chatgpt",label:"ChatGPT",sub:"Pro",color:"#60A5FA"},
  {id:"claude",label:"Claude",sub:"Max",color:"#F59E0B"},
  {id:"gemini",label:"Gemini",sub:"Ultra",color:"#F472B6"},
];
const IT_TEAM = [
  {id:"dev",name:"Developer",color:"#3B82F6"},
  {id:"crit",name:"Critic",color:"#F59E0B"},
  {id:"test",name:"Tester",color:"#10B981"},
];
const FILES = [
  {name:"controller/main.py",folder:false},
  {name:"wintrip_brain/",folder:true},
  {name:"agents/",folder:true},
  {name:"sandbox/",folder:true},
  {name:"persona/",folder:true},
];
const {useState,useRef,useEffect} = React;
function Avatar({name,color,size=26}){
  return <div style={{width:size,height:size,borderRadius:"50%",background:color||"#374151",display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,fontSize:9,fontWeight:600,color:"#fff"}}>{name.slice(0,2).toUpperCase()}</div>;
}
function Dot({on}){return <span style={{display:"inline-block",width:7,height:7,borderRadius:"50%",background:on?"#10B981":"#EF4444",flexShrink:0}}/>;}

function App(){
  const [provider,setProvider] = useState("ollama");
  const [model,setModel] = useState("qwen2.5-coder:7b");
  const [modelOpen,setModelOpen] = useState(false);
  const [team,setTeam] = useState({dev:true,crit:false,test:false});
  const [msgs,setMsgs] = useState([{role:"system",name:"WintripAI",content:"Waakbewustzijn online. Backend verbinden...",ts:"--:--"}]);
  const [input,setInput] = useState("");
  const [statusOpen,setStatusOpen] = useState(true);
  const [filesOpen,setFilesOpen] = useState(false);
  const [serverOn,setServerOn] = useState(false);
  const [memories,setMemories] = useState(133);
  const [dockerOn,setDockerOn] = useState(false);
  const bottomRef = useRef(null);

  useEffect(()=>{
    const check = ()=>{
      fetch(B+"/health").then(r=>r.json()).then(d=>{
        setServerOn(true);
        if(d.memories) setMemories(d.memories);
        if(d.docker!==undefined) setDockerOn(d.docker);
      }).catch(()=>setServerOn(false));
    };
    check();
    const t = setInterval(check,4000);
    return ()=>clearInterval(t);
  },[]);

  useEffect(()=>{ bottomRef.current&&bottomRef.current.scrollIntoView({behavior:"smooth"}); },[msgs]);

  const ts = ()=>new Date().toLocaleTimeString("nl-NL",{hour:"2-digit",minute:"2-digit"});
  const addMsg = (content,name="WintripAI",role="system")=>setMsgs(p=>[...p,{role,name,content,ts:ts()}]);

  function switchProvider(pid){
    setProvider(pid);setModelOpen(false);
    if(pid==="grok") setModel("grok-3");
    else if(pid==="ollama") setModel("qwen2.5-coder:7b");
  }
  function toggleTeam(id){setTeam(p=>({...p,[id]:!p[id]}));}

  async function sendMsg(){
    if(!input.trim()) return;
    const text=input;
    setMsgs(p=>[...p,{role:"user",name:"Philip",content:text,ts:ts()}]);
    setInput("");
    if(!serverOn){addMsg("Backend offline — herstart start_wintrip.py","WintripAI","system");return;}
    const active=IT_TEAM.filter(m=>team[m.id]);
    try{
      const endpoint = active.length ? "/team/discuss" : "/ask";
      const body = active.length
        ? {message:text,model,members:active.map(m=>m.name.toLowerCase())}
        : {prompt:text,model};
      const res = await fetch(B+endpoint,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      const data = await res.json();
      if(active.length && data.discussion){
        data.discussion.forEach(d=>{
          const mem=IT_TEAM.find(m=>m.name.toLowerCase()===d.role.toLowerCase())||{name:d.role,color:"#7c3aed"};
          setMsgs(p=>[...p,{role:"assistant",name:mem.name,content:d.content,ts:ts()}]);
        });
      } else {
        const reply=data.response||data.message||data.result||JSON.stringify(data);
        addMsg(reply,active[0]?.name||"WintripAI","assistant");
      }
    }catch(e){addMsg("Fout: "+e.message,"WintripAI","system");}
  }

  function onKey(e){if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendMsg();}}
  const models=provider==="grok"?GROK_MODELS:OLLAMA_MODELS;
  const showPicker=provider==="ollama"||provider==="grok";
  const activeNames=IT_TEAM.filter(m=>team[m.id]).map(m=>m.name);
  const prov=PROVIDERS.find(p=>p.id===provider);

  return(
    <div style={{display:"flex",height:"100vh",background:"#0f1117",color:"#e2e8f0",overflow:"hidden"}}>
      <div style={{width:215,background:"#151821",borderRight:"1px solid #1e2535",display:"flex",flexDirection:"column",flexShrink:0}}>
        <div style={{padding:"13px 12px 10px",borderBottom:"1px solid #1e2535"}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
            <span style={{fontWeight:600,fontSize:14,color:"#60a5fa"}}>⬡ WintripAI</span>
            <span style={{fontSize:10,padding:"2px 8px",borderRadius:10,background:serverOn?"rgba(16,185,129,0.15)":"rgba(239,68,68,0.15)",color:serverOn?"#10b981":"#ef4444",fontWeight:500}}>{serverOn?"● Online":"● Offline"}</span>
          </div>
          <button style={{display:"flex",alignItems:"center",gap:6,width:"100%",background:"#1e2535",border:"1px solid #2d3748",color:"#6b7280",borderRadius:6,padding:"6px 10px",fontSize:12}}>+ Nieuwe chat</button>
        </div>

        <div style={{padding:"10px 12px",borderBottom:"1px solid #1e2535"}}>
          <div style={{fontSize:10,color:"#374151",textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:500,marginBottom:6}}>Vergadertafel</div>
          {IT_TEAM.map(m=>{const on=team[m.id];return(
            <div key={m.id} onClick={()=>toggleTeam(m.id)} style={{display:"flex",alignItems:"center",gap:7,padding:"5px 8px",borderRadius:6,cursor:"pointer",marginBottom:3,background:on?"rgba(59,130,246,0.07)":"transparent",border:"1px solid "+(on?"#2563eb22":"transparent")}}>
              <div style={{width:6,height:6,borderRadius:"50%",background:on?m.color:"#2d3748",flexShrink:0}}/>
              <span style={{flex:1,fontSize:12,color:on?"#93c5fd":"#4b5563"}}>{m.name}</span>
              <span style={{color:on?"#3b82f6":"#2d3748",fontSize:11}}>{on?"✓":""}</span>
            </div>
          );})}
        </div>

        <div style={{flex:1,overflowY:"auto",padding:"8px 0"}}>
          <div style={{fontSize:10,color:"#374151",textTransform:"uppercase",letterSpacing:"0.08em",fontWeight:500,padding:"0 12px",marginBottom:4}}>Chats</div>
          <div style={{display:"flex",alignItems:"center",gap:7,padding:"5px 12px",color:"#6b7280",background:"#1e2535",margin:"0 8px",borderRadius:6,fontSize:12}}>💬 Nieuwe chat</div>
        </div>

        <div style={{borderTop:"1px solid #1e2535"}}>
          <div onClick={()=>setFilesOpen(p=>!p)} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"7px 12px",cursor:"pointer",color:"#4b5563",fontSize:11}}>
            <span>📁 Bestanden</span><span>{filesOpen?"▾":"▸"}</span>
          </div>
          {filesOpen&&FILES.map((f,i)=>(
            <div key={i} style={{display:"flex",alignItems:"center",gap:6,padding:"3px 12px 3px 20px",color:"#374151",fontSize:11}}>
              {f.folder?"📂":"#"} {f.name}
            </div>
          ))}
        </div>
      </div>

      <div style={{flex:1,display:"flex",flexDirection:"column",minWidth:0}}>
        <div style={{padding:"9px 14px",borderBottom:"1px solid #1e2535",display:"flex",alignItems:"center",justifyContent:"space-between",background:"#151821",flexShrink:0,gap:10,flexWrap:"wrap"}}>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            <span style={{fontWeight:500,fontSize:14,color:"#e2e8f0"}}>Waakbewustzijn</span>
            <span style={{fontSize:10,color:"#374151",background:"#1e2535",padding:"2px 7px",borderRadius:4}}>Phase 6.3</span>
          </div>
          <div style={{display:"flex",alignItems:"center",gap:5,flexWrap:"wrap"}}>
            {PROVIDERS.map(p=>{const on=provider===p.id;return(
              <button key={p.id} onClick={()=>switchProvider(p.id)} style={{display:"flex",alignItems:"center",gap:4,padding:"4px 9px",borderRadius:5,border:"1px solid "+(on?p.color+"55":"#2d3748"),background:on?p.color+"18":"transparent",color:on?p.color:"#4b5563",fontSize:11,fontWeight:on?500:400}}>
                {p.label}<span style={{fontSize:9,opacity:0.65}}>{p.sub}</span>
              </button>
            );})}
            {showPicker&&(
              <div style={{position:"relative"}}>
                <button onClick={()=>setModelOpen(p=>!p)} style={{display:"flex",alignItems:"center",gap:5,background:"#1e2535",border:"1px solid #2d3748",color:"#93c5fd",borderRadius:6,padding:"4px 10px",fontSize:11,fontWeight:500,maxWidth:190}}>
                  ⚙ <span style={{overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",maxWidth:140}}>{model}</span> ▾
                </button>
                {modelOpen&&(
                  <div style={{position:"absolute",top:"100%",right:0,marginTop:4,background:"#1a2030",border:"1px solid #2d3748",borderRadius:8,zIndex:50,width:240,maxHeight:280,overflowY:"auto",boxShadow:"0 8px 32px rgba(0,0,0,0.5)"}}>
                    <div style={{padding:"6px 10px",fontSize:10,color:"#374151",borderBottom:"1px solid #1e2535",textTransform:"uppercase"}}>{provider==="grok"?"Grok API":"Ollama — lokaal"}</div>
                    {models.map(m=>{const sel=m.id===model;return(
                      <div key={m.id} onClick={()=>{setModel(m.id);setModelOpen(false);}} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"7px 10px",cursor:"pointer",background:sel?"rgba(59,130,246,0.12)":"transparent"}}>
                        <span style={{color:sel?"#93c5fd":"#cbd5e1",fontSize:12}}>{m.label}</span>
                        <span style={{fontSize:10,color:"#374151"}}>{m.size}</span>
                      </div>
                    );})}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div style={{flex:1,overflowY:"auto",padding:"18px 18px 8px",display:"flex",flexDirection:"column",gap:14}} onClick={()=>setModelOpen(false)}>
          {msgs.map((m,i)=>{
            const isUser=m.role==="user";
            const tm=IT_TEAM.find(t=>t.name===m.name);
            const color=tm?tm.color:(isUser?"#60a5fa":"#7c3aed");
            return(
              <div key={i} style={{display:"flex",gap:9,alignItems:"flex-start",flexDirection:isUser?"row-reverse":"row"}}>
                {!isUser&&<Avatar name={m.name} color={color} size={26}/>}
                <div style={{display:"flex",flexDirection:"column",maxWidth:"78%",gap:3,alignItems:isUser?"flex-end":"flex-start"}}>
                  <span style={{fontSize:10,color:"#374151"}}>{!isUser&&<span style={{color,fontWeight:500}}>{m.name}{" · "}</span>}{m.ts}</span>
                  <div style={{background:isUser?"#1e3a5f":"#1e2535",borderRadius:8,padding:"7px 11px",lineHeight:1.65,fontSize:13,color:"#e2e8f0",wordBreak:"break-word",whiteSpace:"pre-wrap"}}>{m.content}</div>
                </div>
                {isUser&&<Avatar name="PH" color="#1e3a5f" size={26}/>}
              </div>
            );
          })}
          <div ref={bottomRef}/>
        </div>

        <div style={{background:"#151821",borderTop:"1px solid #1e2535",flexShrink:0}}>
          <div onClick={()=>setStatusOpen(p=>!p)} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"5px 14px",cursor:"pointer",borderBottom:statusOpen?"1px solid #1e2535":"none"}}>
            <span style={{fontSize:10,color:"#374151",fontWeight:500,textTransform:"uppercase",letterSpacing:"0.07em"}}>⚡ System Status</span>
            <span style={{fontSize:10,color:"#374151"}}>{statusOpen?"▾":"▸"}</span>
          </div>
          {statusOpen&&(
            <div style={{display:"flex",flexWrap:"wrap"}}>
              {[
                {label:"controller/main.py",on:serverOn,detail:"Port 8000"},
                {label:"ChromaDB",on:serverOn,detail:memories+" memories"},
                {label:"Docker Sandbox",on:dockerOn,detail:"OODA loop"},
              ].map((s,i)=>(
                <div key={i} style={{display:"flex",alignItems:"center",gap:7,padding:"5px 14px",flex:"1 1 33%",minWidth:130}}>
                  <Dot on={s.on}/><span style={{flex:1,color:s.on?"#94a3b8":"#374151",fontSize:11}}>{s.label}</span>
                  <span style={{fontSize:10,color:s.on?"#10b981":"#ef4444"}}>{s.detail}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={{padding:"10px 14px",borderTop:"1px solid #1e2535",background:"#151821",flexShrink:0}}>
          {activeNames.length>0&&(
            <div style={{display:"flex",gap:5,marginBottom:7,flexWrap:"wrap"}}>
              {activeNames.map(n=>{const tm=IT_TEAM.find(t=>t.name===n);return(
                <span key={n} style={{fontSize:10,padding:"2px 8px",borderRadius:12,background:"rgba(59,130,246,0.08)",color:tm?tm.color:"#60a5fa",border:"1px solid "+(tm?tm.color+"33":"#3b82f633")}}>{n}</span>
              );})}
            </div>
          )}
          <div style={{display:"flex",alignItems:"flex-end",gap:7,background:"#1e2535",borderRadius:10,padding:"7px 9px",border:"1px solid #2d3748"}}>
            <button style={{background:"transparent",border:"none",color:"#374151",padding:3,fontSize:16}}>📎</button>
            <textarea style={{flex:1,background:"transparent",border:"none",outline:"none",color:"#e2e8f0",fontSize:13,resize:"none",maxHeight:120,lineHeight:1.5,fontFamily:"inherit"}}
              placeholder={"Geef een opdracht"+(activeNames.length?" aan "+activeNames.join(", "):"")+"…"}
              value={input} onChange={e=>setInput(e.target.value)} onKeyDown={onKey} rows={1}/>
            <button style={{background:"transparent",border:"none",color:"#374151",padding:3,fontSize:16}}>🎤</button>
            <button onClick={sendMsg} style={{background:"#3b82f6",border:"none",color:"#fff",padding:"5px 9px",borderRadius:6,fontSize:13,opacity:input.trim()?1:0.4}}>➤</button>
          </div>
          <div style={{textAlign:"center",marginTop:5,fontSize:10,color:"#2d3748"}}>{prov?prov.label:""} · {model} · {serverOn?"localhost:8000 online":"server offline"}</div>
        </div>
      </div>
    </div>
  );
}
ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
</script></body></html>"""

# ── IDE HTTP handler ─────────────────────────────────────────────────────────
class IDEHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        ide_path = os.path.join(WINTRIP_ROOT, IDE_FILE)
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        if os.path.exists(ide_path):
            with open(ide_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.wfile.write(IDE_HTML.encode("utf-8"))
    def log_message(self, *args):
        pass  # stil houden

def start_ide_server():
    server = HTTPServer(("127.0.0.1", IDE_PORT), IDEHandler)
    server.serve_forever()

def start_backend():
    global backend_proc
    print("▶  Backend starten op poort 8000...")
    backend_proc = subprocess.Popen(
        [VENV_PYTHON, "-m", "uvicorn", "main:app",
         "--host", "0.0.0.0", "--port", str(BACKEND_PORT)],
        cwd=CONTROLLER,
    )

def shutdown(sig=None, frame=None):
    print("\n⏹  WintripAI wordt gestopt...")
    if backend_proc and backend_proc.poll() is None:
        backend_proc.terminate()
        backend_proc.wait()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Stop eventuele oude processen
    os.system("lsof -ti:8000 | xargs kill -9 2>/dev/null")
    os.system("lsof -ti:3000 | xargs kill -9 2>/dev/null")

    start_backend()
    time.sleep(2)

    # IDE server in achtergrond thread
    t = threading.Thread(target=start_ide_server, daemon=True)
    t.start()

    print(f"✅  WintripAI IDE → http://localhost:{IDE_PORT}")
    print("   Druk op Ctrl+C om te stoppen.\n")
    time.sleep(1)
    webbrowser.open(f"http://localhost:{IDE_PORT}")

    # Wacht tot backend stopt
    backend_proc.wait()
