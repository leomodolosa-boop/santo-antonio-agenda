const CACHE_NAME = 'agenda-sao-v1';
const ASSETS_ESTATICOS = [
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS_ESTATICOS))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((chaves) =>
      Promise.all(chaves.filter((c) => c !== CACHE_NAME).map((c) => caches.delete(c)))
    )
  );
  self.clients.claim();
});

// Só ativos estáticos (ícones/manifest) passam por cache. Páginas do app
// (calendário, jogos, times) sempre buscam da rede, para o app nunca
// mostrar dados ou versão desatualizada.
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((resposta) => resposta || fetch(event.request))
    );
  }
});
