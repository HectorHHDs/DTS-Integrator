/* ======================================================
   NeepMeat Trifecta — Ticketing System JS
====================================================== */

// ─── State ────────────────────────────────────────────
let currentUser     = null;
let allTags         = [];
let allUsers        = [];
let allTickets      = [];
let activeTicket    = null;
let closingTicketId = null;

// ─── DOM refs ─────────────────────────────────────────
const sidebar        = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const hamburger      = document.getElementById('hamburger');
const sidebarClose   = document.getElementById('sidebarClose');
const topbar         = document.querySelector('.topbar');
const themeToggle    = document.getElementById('themeToggle');
const themeIcon      = themeToggle.querySelector('.theme-icon');
const logoutBtn      = document.getElementById('logoutBtn');
const newTicketBtn   = document.getElementById('newTicketBtn');
const guestSignInBtn = document.getElementById('guestSignInBtn');

// Pages
const loginPage   = document.getElementById('loginPage');
const ticketsPage = document.getElementById('ticketsPage');
const usersPage   = document.getElementById('usersPage');
const tagsPage    = document.getElementById('tagsPage');
const tosPage     = document.getElementById('tosPage');
const privacyPage = document.getElementById('privacyPage');

// Nav items
const navItems = document.querySelectorAll('.nav-item');

// ─── API helper ───────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, credentials: 'same-origin' };

  if (body) {
    if (body instanceof FormData) {
      opts.body = body;
    } else {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(body);
    }
  }

  const res  = await fetch('/api' + path, opts);
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

// ─── Theme ────────────────────────────────────────────
const html       = document.documentElement;
const savedTheme = localStorage.getItem('theme') || 'dark';
html.setAttribute('data-theme', savedTheme);
updateThemeIcon(savedTheme);

themeToggle.addEventListener('click', () => {
  const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateThemeIcon(next);
});

function updateThemeIcon(t) {
  themeIcon.textContent = t === 'dark' ? '☀️' : '🌙';
}

// ─── Sidebar toggle ───────────────────────────────────
let sidebarCollapsed = false;

function openSidebar() {
  sidebar.classList.add('open');
  sidebar.classList.remove('collapsed');
  sidebarOverlay.classList.add('active');
  sidebarCollapsed = false;
  topbar.classList.remove('sidebar-collapsed');
}

function closeSidebar() {
  if (window.innerWidth <= 768) {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('active');
  } else {
    sidebar.classList.add('collapsed');
    sidebarCollapsed = true;
    topbar.classList.add('sidebar-collapsed');
    document.querySelector('.main-content').style.marginLeft = '0';
  }
}

function toggleSidebar() {
  if (window.innerWidth <= 768) {
    if (sidebar.classList.contains('open')) closeSidebar();
    else openSidebar();
  } else {
    if (sidebarCollapsed) {
      sidebar.classList.remove('collapsed');
      sidebarCollapsed = false;
      topbar.classList.remove('sidebar-collapsed');
      document.querySelector('.main-content').style.marginLeft = '';
    } else {
      closeSidebar();
    }
  }
}

hamburger.addEventListener('click', toggleSidebar);
sidebarClose.addEventListener('click', closeSidebar);
sidebarOverlay.addEventListener('click', closeSidebar);

// ─── Scroll animations ────────────────────────────────
const observer = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add('visible'); observer.unobserve(e.target); }
  });
}, { threshold: 0.1 });

function observeFades() {
  document.querySelectorAll('.fade-up:not(.visible)').forEach(el => observer.observe(el));
}

// ─── Auth ─────────────────────────────────────────────
document.getElementById('loginBtn').addEventListener('click', doLogin);
document.getElementById('loginPassword').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });

async function doLogin() {
  const username = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value;
  const errEl    = document.getElementById('loginError');
  errEl.textContent = '';

  if (!username || !password) { errEl.textContent = 'Fill in all fields.'; return; }

  const { ok, data } = await api('POST', '/login', { username, password });
  if (!ok) { errEl.textContent = data.error || 'Login failed.'; return; }

  currentUser = data;
  onLogin();
}

async function checkSession() {
  const { ok, data } = await api('GET', '/me');
  if (ok && data) { currentUser = data; await onLogin(); }
  else await onGuest();
}

async function onGuest() {
  // Show the tickets page in read-only mode without requiring login
  document.getElementById('userDisplayName').textContent = 'Guest';
  document.getElementById('userRoleDisplay').textContent = 'not signed in';
  document.getElementById('userAvatar').textContent      = '?';
  document.getElementById('userAvatar').style.cssText    = '';
  document.getElementById('addTagBtn').style.display     = 'none';
  document.getElementById('addUserBtn').style.display    = 'none';
  logoutBtn.style.display    = 'none';
  newTicketBtn.style.display = 'none';
  guestSignInBtn.style.display = 'block';
  await loadTags();
  loadUsers();
  showPage('tickets');
  await loadTickets();
}

guestSignInBtn.addEventListener('click', () => {
  guestSignInBtn.style.display = 'none';
  // Restore login page
  loginPage.classList.remove('hidden');
  ticketsPage.classList.add('hidden');
  document.getElementById('loginCard').style.display    = '';
  document.getElementById('registerCard').style.display = 'none';
  observeFades();
});

function _avatarUrl(avatarFilename) {
  return avatarFilename ? `/uploads/${avatarFilename}` : '';
}

function _renderUserChip() {
  const chipAvatar = document.getElementById('userAvatar');
  const url = _avatarUrl(currentUser.avatar);
  if (url) {
    chipAvatar.style.cssText = `background-image:url(${url});background-size:cover;background-position:center;color:transparent;`;
    chipAvatar.textContent = '';
  } else {
    chipAvatar.style.cssText = '';
    chipAvatar.textContent = currentUser.username[0].toUpperCase();
  }
}

async function onLogin() {
  document.getElementById('userDisplayName').textContent = currentUser.username;
  document.getElementById('userRoleDisplay').textContent = currentUser.role;
  _renderUserChip();
  document.getElementById('addTagBtn').style.display     = currentUser.role === 'administrator' ? '' : 'none';
  document.getElementById('addUserBtn').style.display    = currentUser.role === 'administrator' ? '' : 'none';
  logoutBtn.style.display       = 'block';
  newTicketBtn.style.display    = 'block';
  newTicketBtn.style.marginLeft = 'auto';
  guestSignInBtn.style.display  = 'none';

  // Load tags first so the filter picker is ready, then show page, then load tickets
  await loadTags();
  loadUsers();
  showPage('tickets');
  await loadTickets();
}

logoutBtn.addEventListener('click', async () => {
  await api('POST', '/logout');
  currentUser = null;
  logoutBtn.style.display    = 'none';
  newTicketBtn.style.display = 'none';
  await onGuest();
});

function showLogin() {
  loginPage.classList.remove('hidden');
  ticketsPage.classList.add('hidden');
  usersPage.classList.add('hidden');
  tagsPage.classList.add('hidden');

  // Always start on the login card when showing the login page
  document.getElementById('loginCard').style.display    = '';
  document.getElementById('registerCard').style.display = 'none';

  observeFades();
}

// ─── Register toggle ──────────────────────────────────
document.getElementById('showRegister').addEventListener('click', e => {
  e.preventDefault();
  document.getElementById('loginCard').style.display    = 'none';
  document.getElementById('registerCard').style.display = '';
});

document.getElementById('showLogin').addEventListener('click', e => {
  e.preventDefault();
  document.getElementById('registerCard').style.display = 'none';
  document.getElementById('loginCard').style.display    = '';
});

document.getElementById('registerBtn').addEventListener('click', async () => {
  const username = document.getElementById('regUser').value.trim();
  const password = document.getElementById('regPass').value;
  const email    = document.getElementById('regEmail').value.trim();
  const errEl    = document.getElementById('regError');
  errEl.textContent = '';

  if (!username || !password) { errEl.textContent = 'Fill in all fields.'; return; }

  const { ok, data } = await api('POST', '/register', { username, password, email });
  if (ok) {
    // Switch back to login with a success hint
    document.getElementById('registerCard').style.display = 'none';
    document.getElementById('loginCard').style.display    = '';
    document.getElementById('loginError').textContent     = '';
    document.getElementById('loginUsername').value        = username;
    document.getElementById('loginPassword').value        = '';
    document.getElementById('loginPassword').focus();
  } else {
    errEl.textContent = data.error || 'Registration failed.';
  }
});

// ─── Navigation ───────────────────────────────────────
navItems.forEach(item => {
  item.addEventListener('click', e => {
    e.preventDefault();
    const page = item.dataset.page;
    // All pages are viewable; write actions are blocked at the API/UI level
    showPage(page);
    if (page === 'tickets') loadTickets();
    if (window.innerWidth <= 768) closeSidebar();
  });
});

function showPage(name) {
  [loginPage, ticketsPage, usersPage, tagsPage, tosPage, privacyPage].forEach(p => p.classList.add('hidden'));
  navItems.forEach(n => n.classList.remove('active'));

  const pages  = { tickets: ticketsPage, users: usersPage, tags: tagsPage, tos: tosPage, privacy: privacyPage };
  const titles = { tickets: 'Tickets', users: 'Users', tags: 'Tags', tos: 'Terms of Service', privacy: 'Privacy' };
  const page   = pages[name];
  if (!page) return;

  page.classList.remove('hidden');
  document.getElementById('topbarTitle').textContent = titles[name] || name;
  document.querySelector(`.nav-item[data-page="${name}"]`)?.classList.add('active');

  // Force all fade-up elements visible immediately — the IntersectionObserver
  // can't fire reliably on elements that were just unhidden, so we skip it
  // for page transitions and mark them visible right away.
  page.querySelectorAll('.fade-up').forEach(el => el.classList.add('visible'));

  if (name === 'users') renderUsers();
  if (name === 'tags')  renderTags();
}

// ─── Tags ─────────────────────────────────────────────
async function loadTags() {
  const { ok, data } = await api('GET', '/tags');
  if (ok) {
    allTags = data;
    populateFilterTag();
  }
}

function renderTags() {
  const list = document.getElementById('tagsList');
  list.innerHTML = '';
  if (!allTags.length) {
    list.innerHTML = '<div class="loading-state">No tags yet. Create one above.</div>';
    return;
  }
  allTags.forEach((tag, i) => {
    const card = document.createElement('div');
    card.className = 'tag-card';
    card.style.animationDelay = `${i * 0.05}s`;
    card.innerHTML = `
      <span class="tag-color-dot" style="background:${tag.color}"></span>
      <span class="tag-card-name">${esc(tag.name)}</span>
      ${currentUser?.role === 'administrator'
        ? `<button class="tag-del-btn" data-id="${tag.id}" title="Delete tag">✕</button>` : ''}
    `;
    card.querySelector('.tag-del-btn')?.addEventListener('click', () => deleteTag(tag.id));
    list.appendChild(card);
  });
}

async function deleteTag(id) {
  const { ok } = await api('DELETE', `/tags/${id}`);
  if (ok) { await loadTags(); renderTags(); }
}

// Add tag sheet
document.getElementById('addTagBtn').addEventListener('click', () => {
  if (currentUser?.role !== 'administrator') return;
  openSheet('addTag');
});
document.getElementById('addTagClose').addEventListener('click', () => closeSheet('addTag'));
document.getElementById('addTagOverlay').addEventListener('click', () => closeSheet('addTag'));

const tagColorInput = document.getElementById('tagColor');
const tagColorHex   = document.getElementById('tagColorHex');
tagColorInput.addEventListener('input', () => { tagColorHex.textContent = tagColorInput.value; });

document.getElementById('confirmAddTagBtn').addEventListener('click', async () => {
  const name  = document.getElementById('tagName').value.trim();
  const color = tagColorInput.value;
  const errEl = document.getElementById('tagError');
  errEl.textContent = '';
  if (!name) { errEl.textContent = 'Enter a tag name.'; return; }
  const { ok, data } = await api('POST', '/tags', { name, color });
  if (!ok) { errEl.textContent = data.error || 'Error.'; return; }
  document.getElementById('tagName').value = '';
  await loadTags();
  renderTags();
  closeSheet('addTag');
});

// ─── Users ────────────────────────────────────────────
async function loadUsers() {
  const { ok, data } = await api('GET', '/users');
  if (ok) allUsers = data;
}

function renderUsers() {
  const container = document.getElementById('usersList');
  container.innerHTML = '';

  if (!allUsers.length) {
    container.innerHTML = '<div class="loading-state">No users found.</div>';
    return;
  }

  const isAdmin = currentUser?.role === 'administrator';

  allUsers.forEach((u, i) => {
    const card = document.createElement('div');
    card.className = 'user-card';
    card.style.animationDelay = `${i * 0.04}s`;

    const initials = u.username.slice(0, 2).toUpperCase();
    const roleClass = u.role === 'administrator' ? 'administrator' : u.role === 'contributor' ? 'contributor' : 'user';
    const isSelf = currentUser && u.username === currentUser.username;

    card.innerHTML = `
      <div class="user-card-avatar">${initials}</div>
      <div class="user-card-info">
        <div class="user-card-name">
          ${esc(u.username)}
          ${isSelf ? '<span class="user-card-you">you</span>' : ''}
        </div>
        ${isAdmin && u.recovery_email
          ? `<div class="user-card-email">${esc(u.recovery_email)}</div>`
          : ''}
      </div>
      <div class="user-card-right">
        <span class="role-badge ${roleClass}">${u.role}</span>
        ${isAdmin ? `
          <button class="btn btn-sm btn-outline" onclick="openResetPass(${u.id}, '${esc(u.username)}')">Reset password</button>
          <button class="btn btn-sm btn-outline" style="color:var(--color-danger,#e53e3e);border-color:var(--color-danger,#e53e3e);" onclick="invalidateSessions(${u.id}, '${esc(u.username)}')">Invalidate sessions</button>
        ` : ''}
      </div>
    `;
    container.appendChild(card);
  });
}

let resetUserId = null;
window.openResetPass = (id, name) => {
  resetUserId = id;
  document.getElementById('resetUserLabel').textContent = `Setting new password for: ${name}`;
  openSheet('resetPass');
};

window.invalidateSessions = async (id, name) => {
  if (!confirm(`Invalidate all active sessions for "${name}"? They will be logged out immediately.`)) return;
  const { ok, data } = await api('POST', `/users/${id}/invalidate-sessions`);
  if (ok) {
    alert(`All sessions for "${name}" have been invalidated.`);
  } else {
    alert(data.error || 'Error invalidating sessions.');
  }
};

document.getElementById('confirmResetBtn').addEventListener('click', async () => {
  const password = document.getElementById('resetNewPass').value;
  const { ok, data } = await api('PATCH', `/users/${resetUserId}/reset-password`, { password });
  if (ok) {
    closeSheet('resetPass');
    document.getElementById('resetNewPass').value = '';
    alert('Password updated.');
  } else {
    document.getElementById('resetPassError').textContent = data.error || 'Error.';
  }
});

document.getElementById('resetPassClose').addEventListener('click', () => closeSheet('resetPass'));
document.getElementById('resetPassOverlay').addEventListener('click', () => closeSheet('resetPass'));

// Add user sheet
document.getElementById('addUserBtn').addEventListener('click', () => openSheet('addUser'));
document.getElementById('addUserClose').addEventListener('click', () => closeSheet('addUser'));
document.getElementById('addUserOverlay').addEventListener('click', () => closeSheet('addUser'));

document.getElementById('confirmAddUserBtn').addEventListener('click', async () => {
  const username = document.getElementById('auUsername').value.trim();
  const password = document.getElementById('auPassword').value;
  const role     = document.getElementById('auRole').value;
  const errEl    = document.getElementById('auError');
  errEl.textContent = '';
  if (!username || !password) { errEl.textContent = 'Fill in all fields.'; return; }
  if (password.length < 6)    { errEl.textContent = 'Password must be 6+ chars.'; return; }
  const { ok, data } = await api('POST', '/users', { username, password, role });
  if (!ok) { errEl.textContent = data.error || 'Error.'; return; }
  document.getElementById('auUsername').value = '';
  document.getElementById('auPassword').value = '';
  await loadUsers();
  renderUsers();
  closeSheet('addUser');
});

// ─── Tickets ──────────────────────────────────────────
async function loadTickets() {
  const statusEl = document.getElementById('filterStatus');
  const authorEl = document.getElementById('filterAuthor');
  const sortEl   = document.getElementById('filterSort');
  if (!statusEl || !authorEl || !sortEl) return; // page not ready yet

  const status = statusEl.value;
  const author = authorEl.value;
  const sort   = sortEl.value;

  const selectedTagIds = [...document.querySelectorAll('.filter-tag-pill.selected')].map(el => el.dataset.id);

  let qs = `?status=${status}&sort=${sort}`;
  selectedTagIds.forEach(id => { qs += `&tag=${encodeURIComponent(id)}`; });
  if (author) qs += `&author=${encodeURIComponent(author)}`;

  let ok, httpStatus, data;
  try {
    ({ ok, status: httpStatus, data } = await api('GET', `/tickets${qs}`));
  } catch(e) {
    console.error('loadTickets fetch error:', e);
    return;
  }

  const list = document.getElementById('ticketList');
  if (!list) return;

  if (!ok) {
    const msg = data?.error || `Error loading tickets (HTTP ${httpStatus})`;
    list.innerHTML = `<div class="loading-state" style="color:var(--color-danger, #e53e3e);">${esc(msg)}</div>`;
    return;
  }
  if (!Array.isArray(data) || !data.length) {
    list.innerHTML = '<div class="loading-state">No tickets found.</div>';
    return;
  }

  allTickets = data;
  populateFilterAuthor();

  // Build in a fragment — single atomic DOM swap, no flash
  const fragment = document.createDocumentFragment();
  data.forEach((t, i) => {
    const row = document.createElement('div');
    row.className = 'ticket-row';
    row.style.animationDelay = `${i * 0.04}s`;

    const tagsHtml = t.tags.map(tag =>
      `<span class="tag-badge" style="background:${tag.color}22;color:${tag.color};border:1px solid ${tag.color}55">${esc(tag.name)}</span>`
    ).join('');

    const date = new Date(t.created).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' });

    row.innerHTML = `
      <span class="ticket-status-dot ${t.status}"></span>
      <div class="ticket-info">
        <div class="ticket-title">${esc(t.title)}</div>
        <div class="ticket-meta">
          <span>#${t.id}</span>
          <span>by <strong>${esc(t.author)}</strong></span>
          <span>${date}</span>
          <span class="status-badge ${t.status}">${t.status}</span>
        </div>
        ${tagsHtml ? `<div class="ticket-tags">${tagsHtml}</div>` : ''}
      </div>
    `;
    row.addEventListener('click', () => openTicketDetail(t));
    fragment.appendChild(row);
  });
  list.replaceChildren(fragment);
}
document.getElementById('applyFilters').addEventListener('click', loadTickets);

function populateFilterTag() {
  // Hide the original <select> and use a sibling pill container instead.
  // Never mutate parentNode — that breaks the filters bar on refresh.
  const sel = document.getElementById('filterTag');
  if (sel) sel.style.display = 'none';

  // Collect currently selected IDs from existing pills (if any)
  const currentIds = new Set(
    [...document.querySelectorAll('.filter-tag-pill.selected')].map(el => el.dataset.id)
  );

  // Create the picker once, insert after the hidden select
  let picker = document.getElementById('filterTagPicker');
  if (!picker) {
    picker = document.createElement('div');
    picker.id = 'filterTagPicker';
    picker.style.cssText = 'display:flex;flex-wrap:wrap;gap:0.4rem;align-items:center;';
    if (sel && sel.parentNode) {
      sel.parentNode.insertBefore(picker, sel.nextSibling);
    }
  }
  picker.innerHTML = '';

  allTags.forEach(tag => {
    const pill = document.createElement('span');
    pill.className   = 'tag-badge filter-tag-pill';
    pill.dataset.id  = tag.id;
    pill.textContent = tag.name;
    pill.style.cssText = `background:${tag.color}22;color:${tag.color};border:1px solid ${tag.color}55;cursor:pointer;user-select:none;`;
    if (currentIds.has(String(tag.id))) {
      pill.classList.add('selected');
      pill.style.outline = `2px solid ${tag.color}`;
    }
    pill.addEventListener('click', () => {
      pill.classList.toggle('selected');
      pill.style.outline = pill.classList.contains('selected') ? `2px solid ${tag.color}` : '';
    });
    picker.appendChild(pill);
  });
}

function populateFilterAuthor() {
  const sel = document.getElementById('filterAuthor');
  const cur = sel.value;
  sel.innerHTML = '<option value="">Anyone</option>';
  const seen = new Set();
  allTickets.forEach(t => {
    if (!seen.has(t.author)) {
      seen.add(t.author);
      sel.innerHTML += `<option value="${t.author}" ${cur === t.author ? 'selected' : ''}>${esc(t.author)}</option>`;
    }
  });
}

// ─── Ticket detail sheet ──────────────────────────────
function openTicketDetail(t) {
  activeTicket = t;
  document.getElementById('sheetMeta').innerHTML =
    `<span>#${t.id}</span> &middot; by <strong>${esc(t.author)}</strong> &middot; ${new Date(t.created).toLocaleDateString()} &middot; <span class="status-badge ${t.status}">${t.status}</span>`;
  document.getElementById('sheetTitle').textContent = t.title;
  document.getElementById('sheetDesc').textContent  = t.description;

  // Handle main ticket attachment
  const existingAttachment = document.getElementById('sheetAttachment');
  if (existingAttachment) existingAttachment.remove();

  if (t.attachment) {
    const attachDiv = document.createElement('div');
    attachDiv.id = 'sheetAttachment';
    attachDiv.style.marginTop = '1rem';
    attachDiv.innerHTML = buildAttachmentHtml(t.attachment);
    bindAttachmentPreviews(attachDiv);
    document.getElementById('sheetDesc').after(attachDiv);
  }

  document.getElementById('sheetTags').innerHTML = t.tags.map(tag =>
    `<span class="tag-badge" style="background:${tag.color}22;color:${tag.color};border:1px solid ${tag.color}55">${esc(tag.name)}</span>`
  ).join('');

  // Close block
  const closeBlock = document.getElementById('sheetCloseBlock');
  if (t.status === 'closed' && t.close_msg) {
    closeBlock.classList.add('show');
    closeBlock.innerHTML = `
      <div class="close-by">Closed by ${esc(t.closed_by)}</div>
      <div class="close-msg">${esc(t.close_msg)}</div>
    `;
  } else if (t.status === 'closed') {
    closeBlock.classList.add('show');
    closeBlock.innerHTML = `<div class="close-by">Closed by ${esc(t.closed_by || 'unknown')}</div><div class="close-msg" style="color:var(--color-muted);font-style:italic">No closing message.</div>`;
  } else {
    closeBlock.classList.remove('show');
    closeBlock.innerHTML = '';
  }

  // Action buttons
  const actions = document.getElementById('sheetActions');
  actions.innerHTML = '';

  const canModify = currentUser?.role === 'administrator' || currentUser?.role === 'contributor' || t.author === currentUser?.username;

  if (t.status === 'open' && canModify) {
    const closeBtn = document.createElement('button');
    closeBtn.className   = 'btn btn-danger btn-sm';
    closeBtn.textContent = 'Close ticket';
    closeBtn.addEventListener('click', () => closeTicketSheet(t.id));
    actions.appendChild(closeBtn);
  }

  if (t.status === 'closed' && canModify) {
    const reopenBtn = document.createElement('button');
    reopenBtn.className   = 'btn btn-green btn-sm';
    reopenBtn.textContent = 'Reopen ticket';
    reopenBtn.addEventListener('click', async () => {
      const { ok } = await api('PATCH', `/tickets/${t.id}/reopen`);
      if (ok) { closeSheet('ticketDetail'); await loadTickets(); }
    });
    actions.appendChild(reopenBtn);
  }

  // Show/hide reply area based on login state
  const replyBox = document.querySelector('#ticketDetailSheet .reply-box');
  const guestNote = document.getElementById('guestReplyNote');
  if (currentUser) {
    if (replyBox) replyBox.style.display = '';
    if (guestNote) guestNote.style.display = 'none';
  } else {
    if (replyBox) replyBox.style.display = 'none';
    if (!guestNote) {
      const note = document.createElement('p');
      note.id = 'guestReplyNote';
      note.style.cssText = 'color:var(--color-muted);font-size:0.9rem;margin-top:1rem;';
      note.innerHTML = '<a href="#" id="guestSignInLink" style="color:var(--color-primary);font-weight:600;">Sign in</a> to reply to this ticket.';
      document.getElementById('sheetRepliesList').after(note);
      document.getElementById('guestSignInLink').addEventListener('click', e => {
        e.preventDefault();
        closeSheet('ticketDetail');
        showLogin();
      });
    } else {
      guestNote.style.display = '';
    }
  }
  loadReplies(t.id);
  openSheet('ticketDetail');
}

// ─── Replies ──────────────────────────────────────────
async function loadReplies(tid) {
  const list = document.getElementById('sheetRepliesList');
  // Only show the loading state on first open (list is currently empty)
  if (!list.hasChildNodes()) {
    list.innerHTML = '<div style="color:var(--color-muted); font-size:0.9rem;">Loading replies...</div>';
  }

  const { ok, data } = await api('GET', `/tickets/${tid}/replies`);

  // Build all new nodes in a detached fragment — zero repaints until the swap
  const fragment = document.createDocumentFragment();

  if (!ok || !Array.isArray(data) || !data.length) {
    const empty = document.createElement('div');
    empty.style.cssText = 'color:var(--color-muted);font-size:0.9rem;';
    empty.textContent   = 'No replies yet. Be the first to reply!';
    fragment.appendChild(empty);
  } else {
    data.forEach(r => {
      const el = document.createElement('div');
      el.style.cssText = 'background:var(--color-card);padding:1rem;border-radius:6px;border:1px solid var(--color-border);display:flex;gap:0.75rem;align-items:flex-start;';

      const date = new Date(r.created).toLocaleDateString('en-US', {
        month:'short', day:'numeric', hour:'numeric', minute:'2-digit'
      });

      const attachmentHtml = r.attachment ? buildAttachmentHtml(r.attachment) : '';
      const nameColor      = r.source === 'discord' ? '#5865f2' : 'var(--color-text)';
      const discordIcon    = r.source === 'discord'
        ? ' <span title="Posted via Discord" style="font-size:0.75rem;opacity:0.7;">🎮</span>'
        : '';

      let roleBadge = '';
      if (r.source === 'web' && r.author_role === 'administrator') {
        roleBadge = ' <span style="display:inline-block;font-size:0.65rem;font-weight:700;letter-spacing:0.05em;padding:1px 6px;border-radius:3px;background:#e53e3e22;color:#e53e3e;border:1px solid #e53e3e55;vertical-align:middle;">ADMINISTRATOR</span>';
      } else if (r.source === 'web' && r.author_role === 'contributor') {
        roleBadge = ' <span style="display:inline-block;font-size:0.65rem;font-weight:700;letter-spacing:0.05em;padding:1px 6px;border-radius:3px;background:#38a16922;color:#38a169;border:1px solid #38a16955;vertical-align:middle;">CONTRIBUTOR</span>';
      }

      // Avatar: Discord CDN URL for discord replies, /uploads/ path for web users
      const avatarSrc = r.author_avatar
        ? (r.source === 'discord' ? r.author_avatar : `/uploads/${r.author_avatar}`)
        : '';
      const avatarHtml = avatarSrc
        ? `<img src="${avatarSrc}" style="width:36px;height:36px;border-radius:50%;object-fit:cover;flex-shrink:0;margin-top:2px;" onerror="this.style.display='none'">`
        : `<div style="width:36px;height:36px;border-radius:50%;background:var(--color-border);display:flex;align-items:center;justify-content:center;font-size:0.85rem;font-weight:600;flex-shrink:0;margin-top:2px;color:var(--color-muted);">${esc(r.author[0]?.toUpperCase() || '?')}</div>`;

      el.innerHTML = `
        ${avatarHtml}
        <div style="flex:1;min-width:0;">
          <div style="font-size:0.85rem; color:var(--color-muted); margin-bottom:0.5rem;">
            <strong style="color:${nameColor};">${esc(r.author)}</strong>${discordIcon}${roleBadge} &middot; ${date}
          </div>
          <div style="font-size:0.95rem; line-height: 1.5;">${esc(r.content).replace(/\n/g, '<br>')}</div>
          ${attachmentHtml}
        </div>
      `;
      bindAttachmentPreviews(el);
      fragment.appendChild(el);
    });
  }

  // Single DOM swap — replaces all children atomically, no visible flash
  list.replaceChildren(fragment);
}


document.getElementById('postReplyBtn').addEventListener('click', async () => {
  if (!activeTicket) return;

  const contentEl = document.getElementById('replyContent');
  const fileInput = document.getElementById('replyFile');
  const errEl     = document.getElementById('replyError');
  const content   = contentEl.value.trim();

  errEl.textContent = '';
  if (!content) { errEl.textContent = 'Reply cannot be empty.'; return; }

  const selectedFile = fileInput.files.length > 0 ? fileInput.files[0] : null;
  const fileErr = _checkUserFile(selectedFile);
  if (fileErr) { errEl.textContent = fileErr; return; }

  const formData = new FormData();
  formData.append('content', content);
  if (selectedFile) formData.append('file', selectedFile);

  const { ok, data } = await api('POST', `/tickets/${activeTicket.id}/replies`, formData);
  if (!ok) { errEl.textContent = data.error || 'Error posting reply.'; return; }

  contentEl.value = '';
  fileInput.value = '';

  // Save scroll position of the sheet body before reloading replies
  const sheetBody  = document.querySelector('#ticketDetailSheet .sheet-body');
  const scrollTop  = sheetBody ? sheetBody.scrollTop : 0;

  await loadReplies(activeTicket.id);

  // Restore scroll position then nudge to the bottom so the new reply is visible
  if (sheetBody) {
    sheetBody.scrollTop = sheetBody.scrollHeight;
  }
});

document.getElementById('sheetClose').addEventListener('click', () => closeSheet('ticketDetail'));
document.getElementById('ticketDetailOverlay').addEventListener('click', () => closeSheet('ticketDetail'));

// ─── Close-ticket sheet ───────────────────────────────
function closeTicketSheet(id) {
  closingTicketId = id;
  document.getElementById('closeMessage').value    = '';
  document.getElementById('closeError').textContent = '';
  closeSheet('ticketDetail');
  setTimeout(() => openSheet('closeTicket'), 100);
}

document.getElementById('closeSheetClose').addEventListener('click', () => closeSheet('closeTicket'));
document.getElementById('cancelCloseBtn').addEventListener('click', () => closeSheet('closeTicket'));
document.getElementById('closeTicketOverlay').addEventListener('click', () => closeSheet('closeTicket'));

document.getElementById('confirmCloseBtn').addEventListener('click', async () => {
  const message = document.getElementById('closeMessage').value.trim();
  const { ok, data } = await api('PATCH', `/tickets/${closingTicketId}/close`, { message });
  if (!ok) { document.getElementById('closeError').textContent = data.error || 'Error.'; return; }
  closeSheet('closeTicket');
  await loadTickets();
});

// ─── New ticket sheet ─────────────────────────────────
newTicketBtn.addEventListener('click', () => {
  document.getElementById('ntTitle').value  = '';
  document.getElementById('ntDesc').value   = '';
  document.getElementById('ntError').textContent = '';
  renderTagPicker();
  openSheet('newTicket');
});

document.getElementById('newTicketClose').addEventListener('click', () => closeSheet('newTicket'));
document.getElementById('newTicketOverlay').addEventListener('click', () => closeSheet('newTicket'));

function renderTagPicker() {
  const picker = document.getElementById('ntTagPicker');
  picker.innerHTML = '';
  allTags.forEach(tag => {
    const span = document.createElement('span');
    span.className        = 'tag-badge tag-pick-item';
    span.textContent      = tag.name;
    span.style.background = `${tag.color}22`;
    span.style.color      = tag.color;
    span.style.border     = `1px solid ${tag.color}55`;
    span.dataset.id       = tag.id;
    span.addEventListener('click', () => span.classList.toggle('selected'));
    picker.appendChild(span);
  });
}

document.getElementById('submitTicketBtn').addEventListener('click', async () => {
  const title       = document.getElementById('ntTitle').value.trim();
  const description = document.getElementById('ntDesc').value.trim();
  const fileInput   = document.getElementById('ntFile');
  const errEl       = document.getElementById('ntError');
  errEl.textContent = '';

  if (!title)       { errEl.textContent = 'Title is required.'; return; }
  if (!description) { errEl.textContent = 'Description is required.'; return; }

  const tag_ids = [...document.querySelectorAll('.tag-pick-item.selected')].map(el => el.dataset.id);

  const selectedFile = fileInput.files.length > 0 ? fileInput.files[0] : null;
  const fileErr = _checkUserFile(selectedFile);
  if (fileErr) { errEl.textContent = fileErr; return; }

  const formData = new FormData();
  formData.append('title', title);
  formData.append('description', description);
  formData.append('tag_ids', tag_ids.join(','));
  if (selectedFile) formData.append('file', selectedFile);

  const { ok, data } = await api('POST', '/tickets', formData);
  if (!ok) { errEl.textContent = data.error || 'Error submitting ticket.'; return; }

  fileInput.value = '';
  closeSheet('newTicket');
  await loadTickets();
});

// ─── Sheet system ─────────────────────────────────────
const sheetMap = {
  ticketDetail: { overlay: 'ticketDetailOverlay', sheet: 'ticketDetailSheet' },
  closeTicket:  { overlay: 'closeTicketOverlay',  sheet: 'closeTicketSheet'  },
  newTicket:    { overlay: 'newTicketOverlay',     sheet: 'newTicketSheet'    },
  addUser:      { overlay: 'addUserOverlay',       sheet: 'addUserSheet'      },
  addTag:       { overlay: 'addTagOverlay',        sheet: 'addTagSheet'       },
  resetPass:    { overlay: 'resetPassOverlay',     sheet: 'resetPassSheet'    },
};

function openSheet(name) {
  const { overlay, sheet } = sheetMap[name];
  document.getElementById(overlay).classList.add('active');
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      document.getElementById(sheet).classList.add('open');
    });
  });
  document.body.style.overflow = 'hidden';
}

function closeSheet(name) {
  const { overlay, sheet } = sheetMap[name];
  document.getElementById(sheet).classList.remove('open');
  document.getElementById(overlay).classList.remove('active');
  document.body.style.overflow = '';
}

// ─── Utilities ────────────────────────────────────────
function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ─── Attachment previews ──────────────────────────────
const IMAGE_EXTS = new Set(['png','jpg','jpeg','gif','webp','bmp','svg']);
const VIDEO_EXTS = new Set(['mp4','webm','mov','mkv','avi']);

// Client-side enforcement for 'user' role — images and videos only
function _checkUserFile(file) {
  if (!file) return null;
  if (currentUser?.role !== 'user') return null;
  const ext = file.name.includes('.') ? file.name.split('.').pop().toLowerCase() : '';
  if (!IMAGE_EXTS.has(ext) && !VIDEO_EXTS.has(ext)) {
    return 'Users may only attach images or videos.';
  }
  return null;
}

const FILE_ICONS = {
  py:'🐍', js:'📜', ts:'📜', jsx:'📜', tsx:'📜', html:'🌐', css:'🎨', scss:'🎨',
  java:'☕', c:'⚙️', cpp:'⚙️', h:'⚙️', cs:'⚙️', go:'🐹', rs:'⚙️', rb:'💎',
  php:'🐘', sh:'🖥️', bat:'🖥️', ps1:'🖥️', kt:'📱', swift:'📱', r:'📊', lua:'🌙',
  sql:'🗄️', json:'📋', xml:'📋', yaml:'📋', yml:'📋', toml:'📋', csv:'📊',
  txt:'📄', md:'📝', log:'📄', ini:'⚙️', cfg:'⚙️', conf:'⚙️',
  pdf:'📕', zip:'🗜️', tar:'🗜️', gz:'🗜️', '7z':'🗜️', rar:'🗜️',
};

// Lightbox
const _lb = document.createElement('div');
_lb.id = 'attachLightbox';
_lb.style.cssText = [
  'display:none;position:fixed;inset:0;z-index:9999',
  'background:rgba(0,0,0,0.88);align-items:center;justify-content:center',
  'cursor:zoom-out;flex-direction:column;',
].join(';');
_lb.innerHTML = `
  <button id="lbClose" style="position:absolute;top:1rem;right:1.25rem;background:none;border:none;color:#fff;font-size:2rem;cursor:pointer;line-height:1;">✕</button>
  <div id="lbContent" style="max-width:92vw;max-height:88vh;display:flex;align-items:center;justify-content:center;"></div>
`;
document.body.appendChild(_lb);

function _openLightbox(buildFn) {
  const content = document.getElementById('lbContent');
  content.innerHTML = '';
  buildFn(content);
  _lb.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}
function _closeLightbox() {
  // Pause any playing video before removing it
  const vid = _lb.querySelector('video');
  if (vid) { vid.pause(); vid.src = ''; }
  _lb.style.display = 'none';
  document.body.style.overflow = '';
}
_lb.addEventListener('click', e => { if (e.target === _lb) _closeLightbox(); });
document.getElementById('lbClose').addEventListener('click', _closeLightbox);
document.addEventListener('keydown', e => { if (e.key === 'Escape') _closeLightbox(); });

function buildAttachmentHtml(filename) {
  if (!filename) return '';
  const url      = `/uploads/${filename}`;
  // Strip .zst so the real extension drives rendering (server decompresses transparently)
  const realName = filename.endsWith('.zst') ? filename.slice(0, -4) : filename;
  const ext      = realName.includes('.') ? realName.split('.').pop().toLowerCase() : '';
  const icon     = FILE_ICONS[ext] || '📎';

  if (IMAGE_EXTS.has(ext)) {
    return `
      <div class="attach-preview attach-image" data-url="${url}" style="margin-top:0.75rem;cursor:zoom-in;">
        <img src="${url}" alt="attachment"
          style="max-width:100%;max-height:260px;border-radius:6px;display:block;border:1px solid var(--color-border);object-fit:contain;">
      </div>`;
  }

  if (VIDEO_EXTS.has(ext)) {
    return `
      <div class="attach-preview attach-video" data-url="${url}" style="margin-top:0.75rem;cursor:zoom-in;">
        <video src="${url}" style="max-width:100%;max-height:260px;border-radius:6px;display:block;border:1px solid var(--color-border);"
          preload="metadata" muted></video>
        <div style="font-size:0.75rem;color:var(--color-muted);margin-top:0.3rem;">▶ Click to play fullscreen</div>
      </div>`;
  }

  // Everything else — view as text in new tab, or force-download
  const label = ext ? `.${ext} file` : realName;
  return `
    <div style="margin-top:0.75rem;display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center;">
      <a href="${url}" target="_blank" rel="noopener noreferrer"
        class="btn btn-sm btn-outline"
        style="text-decoration:none;display:inline-flex;align-items:center;gap:0.35rem;">
        <span>${icon}</span><span>${label}</span>
      </a>
      <a href="${url}/download" target="_blank" rel="noopener noreferrer"
        class="btn btn-sm btn-primary"
        style="text-decoration:none;display:inline-flex;align-items:center;gap:0.35rem;">
        <span>↓</span><span>Download</span>
      </a>
    </div>`;
}

function bindAttachmentPreviews(container) {
  container.querySelectorAll('.attach-image').forEach(el => {
    el.addEventListener('click', () => {
      _openLightbox(c => {
        const img = document.createElement('img');
        img.src = el.dataset.url;
        img.style.cssText = 'max-width:92vw;max-height:88vh;border-radius:6px;display:block;object-fit:contain;';
        c.appendChild(img);
      });
    });
  });

  container.querySelectorAll('.attach-video').forEach(el => {
    el.addEventListener('click', () => {
      _openLightbox(c => {
        const vid = document.createElement('video');
        vid.src      = el.dataset.url;
        vid.controls = true;
        vid.autoplay = true;
        vid.style.cssText = 'max-width:92vw;max-height:88vh;border-radius:6px;display:block;';
        c.appendChild(vid);
      });
    });
  });
}

// ─── Avatar upload ────────────────────────────────────
document.getElementById('userChip').addEventListener('click', () => {
  if (!currentUser) return;
  document.getElementById('avatarFileInput').click();
});

document.getElementById('avatarFileInput').addEventListener('change', async e => {
  const file = e.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('avatar', file);
  const { ok, data } = await api('POST', '/me/avatar', formData);
  if (ok) {
    currentUser.avatar = data.avatar;
    _renderUserChip();
  } else {
    alert(data.error || 'Avatar upload failed.');
  }
  e.target.value = '';
});

// ─── Boot ─────────────────────────────────────────────
(async () => {
  await checkSession();
})();
