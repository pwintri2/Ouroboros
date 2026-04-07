export function initModels(){
  const container = document.getElementById('model-badges')
  const models = [
    {name:'gpt-4o', color:'bg-emerald-400'},
    {name:'claude-opus-4', color:'bg-orange-400'},
    {name:'gemini-1.0', color:'bg-sky-400'},
  ]
  for(const m of models){
    const b = document.createElement('button')
    b.className = `${m.color} px-3 py-1 rounded text-sm font-medium`
    b.textContent = m.name
    b.addEventListener('click', ()=>selectModel(m.name, b))
    container.appendChild(b)
  }
}

async function selectModel(name, btn){
  await fetch('/api/models/active', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({model:name})})
  // visual feedback
  Array.from(document.getElementById('model-badges').children).forEach(c=>c.classList.remove('ring-4','ring-cyan-400'))
  btn.classList.add('ring-4','ring-cyan-400')
}
