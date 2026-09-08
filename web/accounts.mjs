import { icon } from '/static/icons.mjs';
export function accountUI({api, node, state, refreshSession, openTab}) {
  const $ = id => document.getElementById(id);
  const labels = {pending:'Chờ duyệt',approved:'Đã duyệt',rejected:'Từ chối'};
  let offset = 0, revision = 0;
  let resetToken = new URLSearchParams(location.hash.split('?')[1] || '').get('token') || '';

  function mode(value) {
    for (const item of ['login','register','forgot']) {
      const el = $('member-' + item);
      if (el) el.hidden = item !== value;
    }
    document.querySelectorAll('[data-auth-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.authMode === value)));
    const msg = $('account-message');
    if (msg) msg.textContent = '';
  }
  document.querySelectorAll('[data-auth-mode]').forEach(b => b.addEventListener('click', () => mode(b.dataset.authMode)));

  function formatCooldown(seconds) {
    if (seconds <= 0) return '0 phút';
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (days > 0) return `${days} ngày ${hours} giờ`;
    if (hours > 0) return `${hours} giờ ${mins} phút`;
    return `${Math.max(1, mins)} phút`;
  }

  function updateCooldowns() {
    const user = state.session?.user;
    if (!user) return;
    const now = Math.floor(Date.now() / 1000);

    // 1. Rename Cooldown: 7 days = 604800s
    const nameLast = Number(user.name_updated_at || 0);
    const nameElapsed = now - nameLast;
    const nameRemain = (7 * 86400) - nameElapsed;
    const nameBox = $('rename-cooldown-box');
    const nameText = $('rename-cooldown-text');
    const nameInput = $('input-new-name');
    const nameBtn = $('btn-submit-rename');

    if (nameInput && !nameInput.matches(':focus')) {
      nameInput.value = user.display_name || '';
    }

    if (nameBox && nameText) {
      if (nameLast > 0 && nameRemain > 0) {
        nameBox.className = 'cooldown-box cooldown-locked';
        nameText.innerHTML = `<strong>Chưa thể đổi tên:</strong> Bạn chỉ có thể đổi tên sau mỗi 7 ngày. Lần đổi tiếp theo sau <strong>${formatCooldown(nameRemain)}</strong>.`;
        if (nameInput) nameInput.disabled = true;
        if (nameBtn) nameBtn.disabled = true;
      } else {
        nameBox.className = 'cooldown-box cooldown-ready';
        nameText.innerHTML = `✓ <strong>Đủ điều kiện:</strong> Bạn có thể cập nhật tên hiển thị mới ngay bây giờ.`;
        if (nameInput) nameInput.disabled = false;
        if (nameBtn) nameBtn.disabled = false;
      }
    }

    // 2. Password Cooldown: 3 days = 259200s
    const passLast = Number(user.password_updated_at || 0);
    const passElapsed = now - passLast;
    const passRemain = (3 * 86400) - passElapsed;
    const passBox = $('password-cooldown-box');
    const passText = $('password-cooldown-text');
    const passBtn = $('btn-submit-password');
    const passInputs = [$('input-current-pass'), $('input-new-pass'), $('input-confirm-pass')];

    if (passBox && passText) {
      if (passLast > 0 && passRemain > 0) {
        passBox.className = 'cooldown-box cooldown-locked';
        passText.innerHTML = `<strong>Chưa thể đổi mật khẩu:</strong> Bạn chỉ có thể đổi mật khẩu sau mỗi 3 ngày. Lần đổi tiếp theo sau <strong>${formatCooldown(passRemain)}</strong>.`;
        passInputs.forEach(i => { if (i) i.disabled = true; });
        if (passBtn) passBtn.disabled = true;
      } else {
        passBox.className = 'cooldown-box cooldown-ready';
        passText.innerHTML = `✓ <strong>Đủ điều kiện:</strong> Bạn có thể đổi mật khẩu mới ngay bây giờ.`;
        passInputs.forEach(i => { if (i) i.disabled = false; });
        if (passBtn) passBtn.disabled = false;
      }
    }
  }

  function sessionChanged() {
    const user = state.session?.user;
    const isAdmin = Boolean(state.session?.admin || user?.role === 'admin');

    $('account-guest').hidden = !!user;
    $('account-member').hidden = !user;

    const navBtn = $('account-nav');
    if (navBtn) {
      navBtn.replaceChildren(...(user ? [icon('user'), document.createTextNode(' Tôi')] : [document.createTextNode('Tài khoản')]));
      navBtn.classList.toggle('logged-in', !!user);
    }

    const adminNav = $('admin-nav');
    if (adminNav) adminNav.hidden = !isAdmin;

    const adminBanner = $('member-admin-banner');
    if (adminBanner) adminBanner.hidden = !isAdmin;

    if (user) {
      $('member-name').textContent = user.display_name || 'Thành viên';
      $('member-email').textContent = user.email || '';

      const nameParts = (user.display_name || 'TV').trim().split(/\s+/);
      const initials = nameParts.length > 1
        ? (nameParts[0][0] + nameParts[nameParts.length - 1][0]).toUpperCase()
        : (nameParts[0].slice(0, 2)).toUpperCase();
      const avatarEl = $('member-avatar');
      if (avatarEl) avatarEl.textContent = initials;

      const roleBadge = $('member-role-badge');
      if (roleBadge) {
        if (isAdmin) {
          roleBadge.replaceChildren(icon('shield'), document.createTextNode('Quản trị viên'));
          roleBadge.className = 'role-badge role-admin';
        } else {
          roleBadge.textContent = 'Thành viên';
          roleBadge.className = 'role-badge role-user';
        }
      }

      const joinedEl = $('member-joined');
      if (joinedEl && user.created_at) {
        const d = new Date(user.created_at);
        joinedEl.textContent = !isNaN(d.getTime()) ? 'Thành viên từ ' + d.toLocaleDateString('vi-VN') : '';
      }

      updateCooldowns();
    } else {
      revision++;
      $('member-contributions').replaceChildren();
      $('member-counts').replaceChildren();
      const detailStats = $('member-detail-stats');
      if (detailStats) detailStats.replaceChildren();
      const rankBadge = $('member-rank-badge');
      if (rankBadge) rankBadge.hidden = true;
    }
  }

  document.querySelectorAll('.subtab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.subtab;
      document.querySelectorAll('.subtab-btn').forEach(b => b.setAttribute('aria-selected', String(b.dataset.subtab === target)));
      $('subpanel-contributions').hidden = target !== 'contributions';
      $('subpanel-settings').hidden = target !== 'settings';
      if (target === 'settings') updateCooldowns();
    });
  });

  const gotoAdminBtn = $('btn-goto-admin');
  if (gotoAdminBtn) {
    gotoAdminBtn.addEventListener('click', () => openTab('admin'));
  }

  function busyForm(id, action, messageId = 'account-message') {
    const form = $(id);
    if (!form) return;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const currentForm = event.currentTarget;
      const data = Object.fromEntries(new FormData(currentForm));
      const controls = [...currentForm.elements].map(e => [e, e.disabled]);
      controls.forEach(([e]) => e.disabled = true);
      const message = $(messageId);
      if (message) {
        message.textContent = 'Đang xử lý…';
        message.classList.remove('error');
      }
      try {
        await action(data, currentForm);
      } catch (error) {
        if (message) {
          message.textContent = error.message;
          message.classList.add('error');
        }
      } finally {
        controls.forEach(([e, disabled]) => e.disabled = disabled);
      }
    });
  }

  for (const action of ['login', 'register']) {
    busyForm('member-' + action, async (data, form) => {
      const res = await api('auth/' + action, data);
      if (res.token) {
        localStorage.setItem('tai_admin_token', res.token);
      }
      form.reset();
      await refreshSession();
      const msg = $('account-message');
      if (msg) msg.textContent = '';
      await loadContributions();
    });
  }

  busyForm('member-forgot', async data => {
    const result = await api('auth/forgot-password', data);
    $('account-message').textContent = result.message;
  });

  busyForm('member-reset', async (data, form) => {
    if (data.password !== data.confirm) throw new Error('Hai mật khẩu chưa khớp nhau.');
    if (!resetToken) throw new Error('Liên kết không hợp lệ. Hãy yêu cầu liên kết mới.');
    const result = await api('auth/reset-password', {password: data.password, token: resetToken});
    resetToken = ''; form.reset();
    await refreshSession();
    mode('login'); await openTab('account');
    $('account-message').textContent = result.message;
  }, 'reset-message');

  $('reset-request-new')?.addEventListener('click', async () => {
    await openTab('account');
    mode('forgot');
  });

  $('member-logout')?.addEventListener('click', async () => {
    const button = $('member-logout');
    button.disabled = true;
    try {
      localStorage.removeItem('tai_admin_token');
      await api('auth/logout', {});
      await refreshSession();
      mode('login');
      $('member-filters')?.reset();
    } catch(error) {
      $('notice').textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });

  busyForm('form-change-name', async (data) => {
    const result = await api('me/profile', { display_name: data.display_name });
    const msg = $('rename-message');
    if (msg) {
      msg.textContent = result.message || 'Đã cập nhật tên hiển thị thành công!';
      msg.className = 'setting-feedback success';
    }
    await refreshSession();
    updateCooldowns();
  }, 'rename-message');

  busyForm('form-change-password', async (data, form) => {
    if (data.new_password !== data.confirm_password) {
      throw new Error('Mật khẩu mới và xác nhận mật khẩu không khớp.');
    }
    const result = await api('me/change-password', {
      current_password: data.current_password,
      new_password: data.new_password,
      confirm_password: data.confirm_password
    });
    form.reset();
    const msg = $('password-message');
    if (msg) {
      msg.textContent = result.message || 'Đã cập nhật mật khẩu thành công!';
      msg.className = 'setting-feedback success';
    }
    await refreshSession();
    updateCooldowns();
  }, 'password-message');

  async function loadContributions(append = false) {
    if (!state.session?.user) return;
    const current = ++revision;
    if (!append) {
      offset = 0;
      $('member-contributions').replaceChildren(node('p', 'Đang tải đóng góp…', 'empty-state'));
    }
    $('member-more').disabled = true;

    try {
      if (!append) {
        try {
          const stats = await api('me/stats');
          if (current === revision) renderStats(stats);
        } catch (e) {}
      }

      const params = new URLSearchParams({
        kind: $('member-kind').value,
        status: $('member-status').value,
        offset: String(offset)
      });
      const data = await api('me/contributions?' + params);
      if (current !== revision) return;

      if (!append) $('member-contributions').replaceChildren();

      for (const item of data.items) {
        const card = node('article', undefined, 'contribution-record');
        const meta = node('div', undefined, 'record-meta');
        meta.append(
          node('span', item.kind === 'word' ? 'TỪ ĐÓNG GÓP' : 'CÂU ĐÓNG GÓP', 'eyebrow'),
          node('span', labels[item.status] || item.status, 'status-badge status-' + item.status)
        );
        card.append(meta, node('h3', item.tai_text || 'Chưa có chữ Tai', 'tai'), node('p', item.romanization || 'Chưa có phiên âm'));
        if (item.meaning) card.append(node('p', item.meaning));
        const date = new Date(item.created_at);
        if (!Number.isNaN(date.getTime())) card.append(node('small', 'Đã gửi ' + date.toLocaleDateString('vi-VN'), 'hint'));
        $('member-contributions').append(card);
      }

      if (!append && !data.items.length) {
        $('member-contributions').append(node('p', 'Bạn chưa có đóng góp nào theo bộ lọc này. Bắt đầu với một từ hoặc một câu quen thuộc nhé.', 'empty-state'));
      }
      offset += data.items.length;
      $('member-more').hidden = !data.has_more;
    } finally {
      if (current === revision) $('member-more').disabled = false;
    }
  }

  function renderStats(stats) {
    const countsContainer = $('member-counts');
    const detailContainer = $('member-detail-stats');
    const rankBadge = $('member-rank-badge');
    if (!countsContainer) return;

    countsContainer.replaceChildren();
    if (detailContainer) detailContainer.replaceChildren();

    if (rankBadge) {
      if (stats.rank) {
        rankBadge.hidden = false;
        rankBadge.textContent = `Hạng #${stats.rank} · ${stats.score} điểm duyệt`;
      } else {
        rankBadge.hidden = true;
      }
    }

    const cards = [
      { label: 'Tổng đóng góp', count: stats.total, cls: 'stat-total' },
      { label: 'Đã duyệt', count: stats.words.approved + stats.sentences.approved, cls: 'stat-approved' },
      { label: 'Chờ duyệt', count: stats.words.pending + stats.sentences.pending, cls: 'stat-pending' },
      { label: 'Từ chối', count: stats.words.rejected + stats.sentences.rejected, cls: 'stat-rejected' }
    ];

    for (const c of cards) {
      const card = node('div', undefined, 'count-card ' + c.cls);
      card.append(node('strong', String(c.count)), node('span', c.label));
      countsContainer.append(card);
    }

    if (detailContainer) {
      const wCard = node('div', undefined, 'detail-stat-card');
      wCard.append(
        node('h4', 'Từ vựng đóng góp'),
        node('p', `Tổng: ${stats.words.total} (${stats.words.approved} đã duyệt · ${stats.words.pending} chờ duyệt · ${stats.words.rejected} từ chối)`)
      );

      const sCard = node('div', undefined, 'detail-stat-card');
      sCard.append(
        node('h4', 'Câu nói đóng góp'),
        node('p', `Tổng: ${stats.sentences.total} (${stats.sentences.approved} đã duyệt · ${stats.sentences.pending} chờ duyệt · ${stats.sentences.rejected} từ chối)`)
      );

      wCard.querySelector('h4').prepend(icon('book'));
      sCard.querySelector('h4').prepend(icon('message'));
      detailContainer.append(wCard, sCard);
    }
  }

  function loadError(error) {
    $('member-contributions').replaceChildren(node('p', error.message, 'empty-state error'));
  }

  $('member-filters')?.addEventListener('submit', event => {
    event.preventDefault();
    loadContributions().catch(loadError);
  });
  $('member-filters')?.addEventListener('reset', () => {
    queueMicrotask(() => loadContributions().catch(loadError));
  });
  $('member-more')?.addEventListener('click', () => loadContributions(true).catch(loadError));

  async function leaderboard() {
    const container=$('leaderboard-results');
    container.replaceChildren(node('p','Đang tải bảng xếp hạng…','empty-state'));
    const data=await api('leaderboard');
    container.replaceChildren();
    if(!data.items.length){container.append(node('p','Bảng xếp hạng đang chờ những đóng góp đầu tiên được duyệt.','empty-state'));return;}
    const table=node('table',undefined,'ranking-table');
    const caption=node('caption','Xếp hạng theo số từ và câu đã duyệt','sr-only');
    const head=node('thead'), tr=node('tr');
    for(const label of ['Hạng','Thành viên','Từ','Câu','Điểm']){const th=node('th',label);th.scope='col';tr.append(th);}
    head.append(tr);const body=node('tbody');
    for(const item of data.items){
      const row=node('tr');
      const rank=node('td');rank.append(node('span',String(item.rank),'rank-number'+(item.rank<=3?' rank-top':'')));
      row.append(rank,node('td',item.display_name),node('td',String(item.words)),node('td',String(item.sentences)),node('td',String(item.total),'rank-total'));
      body.append(row);
    }
    table.append(caption,head,body);container.append(table);
  }
  return {sessionChanged,async open(id){
    if(id==='account')await loadContributions();
    if(id==='leaderboard')await leaderboard();
    if(id==='reset-password'&&!resetToken)$('reset-message').textContent='Liên kết không hợp lệ. Hãy yêu cầu liên kết mới.';
  }};
}
