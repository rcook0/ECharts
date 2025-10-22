
// Inject in DevTools console or as a userscript.
// Sandbox the UI without broker redirects or live sockets.
(function(){
  try { window.lead = window.lead || {}; window.lead.ftd = () => 1; } catch(e) {}
  window.ShowPartner = (...args) => console.log('ShowPartner blocked', args);
  window.io = () => ({ on(){}, emit(){}, close(){}, connected:false });
  console.log('[hook] deposit gate bypassed, partner redirects blocked, sockets muted');
})();
