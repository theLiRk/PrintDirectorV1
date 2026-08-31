const refreshLabel = document.getElementById('last-refresh');
const statusDot = document.querySelector('.status-dot');
const post = async (url) => {
  const response = await fetch(url, { method: 'POST', headers: authHeaders() });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  refreshLabel.textContent = `Updated ${new Date().toLocaleTimeString()}`;
};

document.querySelectorAll('[data-show]').forEach((button) => {
  button.onclick = () => post(`/api/director/show/${button.dataset.show}`).catch(console.error);
});
document.querySelector('[data-action="return-auto"]').onclick = () => {
  post('/api/director/return-auto').catch(console.error);
};
document.querySelectorAll('[data-stream]').forEach((button) => {
  button.onclick = () => post(`/api/stream/${button.dataset.stream}`).catch(console.error);
});

setInterval(() => {
  refreshLabel.textContent = `Live · ${new Date().toLocaleTimeString()}`;
}, 5000);

setInterval(() => {
  const director = document.getElementById('director');
  if (director && director.textContent && !director.textContent.includes('offline')) {
    statusDot.style.background = '#34d399';
  }
}, 1000);