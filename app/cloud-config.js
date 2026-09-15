(() => {
  const params = new URLSearchParams(location.search);
  window.PERSONAL_NEEDS_CLOUD = {
    url: 'https://ilvusmkbnfjdakkolekt.supabase.co',
    publishableKey: 'sb_publishable_prWW8CBhb3WpuYwzYRnj2g_g0GF9Ra0',
    enabled: params.has('cloud') || location.hostname.endsWith('.onrender.com')
  };
})();
