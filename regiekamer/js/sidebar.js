export function initSidebar(){
  document.getElementById('new-chat').addEventListener('click', async ()=>{
    const r = await fetch('/api/chats', {method:'POST'}).then(r=>r.json())
    if(r && r.id){
      loadChat(r.id)
    }
  })
}

async function loadChat(id){
  const res = await fetch(`/api/chats/${id}`)
  const data = await res.json()
  document.getElementById('messages').innerText = ''
  for(const m of data.messages || []){
    const el = document.createElement('div')
    el.textContent = `${m.sender}: ${m.text}`
    document.getElementById('messages').appendChild(el)
  }
}
