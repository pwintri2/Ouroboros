export function initChat(){
  const send = document.getElementById('send')
  const input = document.getElementById('input')
  send.addEventListener('click', async ()=>{
    const text = input.value.trim()
    if(!text) return
    // For now post to /api/chat without chat_id (ephemeral)
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({sender:'user', text})
    })
    const j = await res.json()
    if(j.response){
      appendMessage('user', text)
      appendMessage('assistant', j.response)
      input.value = ''
    }
  })
}

function appendMessage(sender, text){
  const el = document.createElement('div')
  el.className = 'p-2'
  el.textContent = `${sender}: ${text}`
  document.getElementById('messages').appendChild(el)
  document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight
}
