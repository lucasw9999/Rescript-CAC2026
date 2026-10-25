/* Presentation only. No API requests, media URLs, job state or business logic. */
(() => {
  'use strict';
  const assetRoot = new URL('.', document.currentScript.src);
  const byId = id => document.getElementById(id);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const drop = byId('drop');
  drop.addEventListener('keydown', event => {
    if ((event.key === 'Enter' || event.key === ' ') && event.target === drop) {
      event.preventDefault(); byId('file').click();
    }
  });

  // Keep dynamic click targets keyboard-reachable without changing their handlers.
  let fieldId = 0, lastLineFocus = null;
  const lines = byId('lines');
  const recent = byId('recent');
  const enhance = () => {
    for (const li of recent.children) {
      li.tabIndex = 0; li.setAttribute('role', 'button');
      li.setAttribute('aria-label', 'Open recording: ' + li.firstElementChild.textContent);
    }
    for (const li of lines.children) {
      const text = li.querySelector('.text');
      if (text) { text.tabIndex = 0; text.setAttribute('role', 'button'); text.setAttribute('aria-label', 'Play line: ' + text.textContent); }
      const time = li.querySelector('.t');
      if (time) time.setAttribute('aria-label', 'Play line at ' + time.textContent);
      for (const field of li.querySelectorAll('input.ask, textarea')) {
        if (field.dataset.crewLabeled) continue;
        field.id = 'studio-line-field-' + (++fieldId);
        const label = document.createElement('label');
        label.className = 'field-label'; label.htmlFor = field.id;
        label.textContent = field.matches('.ask') ? 'What would you like to change?' : 'Edit this line';
        field.before(label); field.dataset.crewLabeled = 'true';
      }
    }
    // A refreshed script replaces its nodes; restore a detached control's focus.
    if (lastLineFocus && !lastLineFocus.node.isConnected && document.activeElement === document.body) {
      const li = [...lines.children].find(row => row.dataset.i === lastLineFocus.i);
      const target = li?.querySelector(lastLineFocus.selector);
      target?.focus({ preventScroll: true }); lastLineFocus = null;
    }
  };
  const keyClick = event => {
    const target = event.target.closest('[role="button"]');
    if (target && (event.key === 'Enter' || event.key === ' ') && !event.repeat) {
      event.preventDefault(); target.click();
    }
  };
  recent.addEventListener('keydown', keyClick); lines.addEventListener('keydown', keyClick);
  lines.addEventListener('focusin', event => {
    const li = event.target.closest('li[data-i]'); if (!li) return;
    const element = event.target;
    let selector = '.t';
    if (element.matches('.text')) selector = '.text';
    else if (element.matches('[data-act="ask"], input.ask')) selector = '[data-act="ask"]';
    else if (element.closest('.row-actions,.editbar') || element.matches('textarea')) selector = '[data-act="edit"]';
    lastLineFocus = { node: element, i: li.dataset.i, selector };
  });
  const contentObserver = new MutationObserver(enhance);
  contentObserver.observe(recent, { childList: true });
  contentObserver.observe(lines, { childList: true, subtree: true });
  enhance();

  let visual = null, scheduled = false;
  const stepItems = [...byId('steps').children];
  const names = { pip: 'Pip', kit: 'Kit', echo: 'Echo', tempo: 'Tempo', scout: 'Scout' };
  function update() {
    scheduled = false;
    const working = !byId('view-work').hidden, error = !byId('work-error').hidden;
    for (const li of stepItems) {
      const active = li.classList.contains('active'), done = li.classList.contains('done');
      const text = li.querySelector('.step-state');
      if (text) text.textContent = active ? (error ? 'Needs attention' : 'Working') : done ? 'Done' : 'Waiting';
      if (active) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
    }
    const active = working ? stepItems.find(li => li.classList.contains('active') && !li.hidden) : null;
    byId('crew-status').textContent = error ? 'The crew is waiting for you.' : active?.dataset.character ? names[active.dataset.character] + ' is on it.' : 'The crew is getting ready.';
    const view = ['home', 'work', 'result'].find(name => !byId('view-' + name).hidden);
    document.querySelector('.skip-link').href = '#view-' + (view || 'home');
    visual?.setState(view, active, error);
  }
  function schedule() { if (!scheduled) { scheduled = true; requestAnimationFrame(update); } }
  const stateObserver = new MutationObserver(schedule);
  for (const li of stepItems) stateObserver.observe(li, { attributes: true, attributeFilter: ['class', 'hidden'] });
  for (const id of ['view-home', 'view-work', 'view-result', 'work-error']) stateObserver.observe(byId(id), { attributes: true, attributeFilter: ['hidden'] });
  update();

  import(new URL('characters.js', assetRoot).href).then(({ THREE, CAST, createCharacter, createRenderer, setupLighting }) => {
    const canvas = document.createElement('canvas'); canvas.className = 'live-crew'; canvas.setAttribute('aria-hidden', 'true');
    let renderer;
    try { renderer = createRenderer(canvas); } catch { return; }
    const scene = new THREE.Scene(); setupLighting(scene);
    const camera = new THREE.OrthographicCamera(-4, 4, 2, -2, .1, 30);
    camera.position.set(0, 1.1, 7); camera.lookAt(0, .1, 0);
    const models = CAST.map(spec => { const object = createCharacter(spec.id); scene.add(object); return object; });
    const homePositions = [[-2.45, 0, 0], [-1.22, .12, -.12], [0, .2, .1], [1.22, .08, -.12], [2.45, 0, 0]];
    const motion = byId('crew-motion'); motion.hidden = false;
    let host = null, view = null, activeId = null, frame = 0, last = 0, elapsed = 0, paused = false, failed = false, contextLost = false, inViewport = true, error = false;
    function canAnimate() { return !failed && !contextLost && !document.hidden && inViewport && !paused && !reduced.matches && !error && host; }
    function resize() {
      if (!host || failed || contextLost) return;
      const width = host.clientWidth, height = host.clientHeight; if (!width || !height) return;
      renderer.setSize(width, height, false);
      const ratio = width / height, halfW = view === 'home' ? Math.max(3.8, 1.3 * ratio) : Math.max(1.42, 1.42 * ratio), halfH = halfW / ratio;
      camera.left = -halfW; camera.right = halfW; camera.top = halfH; camera.bottom = -halfH; camera.updateProjectionMatrix();
      renderer.render(scene, camera);
    }
    function settle() {
      models.forEach((model, i) => {
        model.visible = view === 'home' || CAST[i].id === activeId;
        model.position.set(...(view === 'home' ? homePositions[i] : [0, 0, 0]));
        model.rotation.set(0, view === 'home' ? (2 - i) * .06 : -.12, 0);
        model.scale.setScalar(view === 'home' ? .9 : 1);
      });
    }
    function animate(now) {
      frame = 0; if (!canAnimate()) return;
      elapsed += Math.min((now - last) / 1000 || 0, .05); last = now;
      models.forEach((model, i) => { if (!model.visible) return; const base = view === 'home' ? homePositions[i][1] : 0; model.position.y = base + Math.sin(elapsed * 1.5 + i) * .055; model.rotation.z = Math.sin(elapsed * 1.15 + i) * .035; });
      renderer.render(scene, camera); frame = requestAnimationFrame(animate);
    }
    function refresh() {
      cancelAnimationFrame(frame); frame = 0; last = 0;
      if (!host || failed || contextLost || document.hidden || !inViewport) return;
      if (paused || reduced.matches || error) settle();
      renderer.render(scene, camera); if (canAnimate()) frame = requestAnimationFrame(animate);
    }
    const resizeObserver = new ResizeObserver(resize);
    const intersection = new IntersectionObserver(entries => { inViewport = entries[0].isIntersecting; refresh(); });
    function setState(nextView, li, nextError) {
      const nextId = li?.dataset.character || null;
      const nextHost = nextView === 'home' ? byId('home-crew') : nextView === 'work' && nextId ? li.querySelector('.crew-slot') : null;
      if (host === nextHost && activeId === nextId && view === nextView && error === nextError) return;
      cancelAnimationFrame(frame); resizeObserver.disconnect(); intersection.disconnect();
      host?.classList.remove('is-3d'); canvas.remove(); host = nextHost; view = nextView; activeId = nextId; error = nextError;
      settle();
      if (host && !failed && !contextLost) { host.append(canvas); host.classList.add('is-3d'); resizeObserver.observe(host); intersection.observe(host); inViewport = true; resize(); refresh(); }
      motion.hidden = !host || failed;
    }
    const onVisibility = () => refresh(), onReduced = () => { settle(); refresh(); };
    document.addEventListener('visibilitychange', onVisibility); reduced.addEventListener('change', onReduced);
    motion.addEventListener('click', () => { paused = !paused; motion.setAttribute('aria-pressed', String(paused)); motion.textContent = paused ? 'Resume crew' : 'Pause crew'; refresh(); });
    canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); contextLost = true; cancelAnimationFrame(frame); host?.classList.remove('is-3d'); motion.hidden = true; });
    canvas.addEventListener('webglcontextrestored', () => { contextLost = false; host?.classList.add('is-3d'); motion.hidden = !host; resize(); refresh(); });
    renderer.debug.onShaderError = (gl, program, vertex, fragment) => {
      console.error('Rescript crew shader error', gl.getProgramInfoLog(program), gl.getShaderInfoLog(vertex), gl.getShaderInfoLog(fragment));
      failed = true; cancelAnimationFrame(frame); host?.classList.remove('is-3d'); canvas.remove(); motion.hidden = true;
    };
    visual = { setState }; update();
    window.addEventListener('pagehide', () => {
      cancelAnimationFrame(frame); resizeObserver.disconnect(); intersection.disconnect();
      document.removeEventListener('visibilitychange', onVisibility); reduced.removeEventListener('change', onReduced);
      contentObserver.disconnect(); stateObserver.disconnect();
      scene.traverse(o => { o.geometry?.dispose(); if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m.dispose()); }); renderer.dispose();
    }, { once: true });
  }).catch(() => { /* Local PNGs are the permanent capability fallback. */ });
})();
