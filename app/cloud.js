(() => {
  const config = window.PERSONAL_NEEDS_CLOUD;
  if (!config?.enabled) return;
  if (!window.supabase?.createClient) throw new Error('Supabase 客户端加载失败');

  const client = window.supabase.createClient(config.url, config.publishableKey);
  const scoreFields = ['pain_score', 'frequency_score', 'time_cost_score', 'automation_potential', 'usage_intent'];
  const weights = [.25, .25, .15, .2, .15];
  let session = null;
  let readyResolve;
  const ready = new Promise(resolve => { readyResolve = resolve; });

  function score(record) {
    const values = scoreFields.map(name => record[name]);
    if (values.some(value => value == null)) return [null, '待补评分'];
    const mean = values.reduce((sum, value, index) => sum + value * weights[index], 0);
    const result = Math.round((mean - 1) / 4 * 100);
    return [result, result >= 80 ? '强项目候选' : result >= 60 ? '值得进一步分析' : result >= 40 ? '值得观察' : '低优先级'];
  }

  async function requireUser() {
    await ready;
    if (!session?.user) throw new Error('请先登录');
    return session.user;
  }

  async function checked(query) {
    const { data, error, count } = await query;
    if (error) {
      if (error.code === '23505' && error.message?.includes('themes_user_id_name_key')) {
        throw new Error('你已经建立过同名主题，请直接使用下方已有主题，或换一个名称。');
      }
      throw new Error(error.message);
    }
    return { data, count };
  }

  async function recordsWithTags(rows) {
    if (!rows.length) return [];
    const ids = rows.map(row => row.id);
    const { data: links } = await checked(client.from('record_tags').select('record_id,tags(id,name,category)').in('record_id', ids));
    const byRecord = new Map();
    for (const link of links || []) {
      if (!link.tags) continue;
      if (!byRecord.has(link.record_id)) byRecord.set(link.record_id, []);
      byRecord.get(link.record_id).push(link.tags);
    }
    return rows.map(row => {
      const [opportunity_score, opportunity_label] = score(row);
      return {...row, tags: byRecord.get(row.id) || [], opportunity_score, opportunity_label};
    });
  }

  async function allRecords(includeArchived = true) {
    let query = client.from('records').select('*');
    if (!includeArchived) query = query.neq('status', 'Archived');
    const { data } = await checked(query.order('occurred_at', {ascending: false}));
    return recordsWithTags(data || []);
  }

  function rank(records, field) {
    return records.filter(record => record[field] != null)
      .sort((a, b) => b[field] - a[field] || new Date(b.occurred_at) - new Date(a.occurred_at)).slice(0, 5);
  }

  function counts(records, selector) {
    const map = new Map();
    for (const record of records) for (const value of selector(record)) map.set(value, (map.get(value) || 0) + 1);
    return [...map].map(([label, value]) => ({label, value})).sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
  }

  function analytics(records) {
    const scored = records.filter(record => record.opportunity_score != null);
    const average = scored.length ? Math.round(scored.reduce((sum, record) => sum + record.opportunity_score, 0) / scored.length) : null;
    return {
      summary: {total_records: records.length, scored_records: scored.length, scoring_completion: records.length ? Math.round(scored.length / records.length * 100) : 0, average_opportunity: average},
      scene_counts: counts(records, record => [record.scene]),
      problem_tag_counts: counts(records, record => record.tags.filter(tag => tag.category === 'problem').map(tag => tag.name)).slice(0, 10),
      rankings: {pain: rank(records, 'pain_score'), frequency: rank(records, 'frequency_score'), automation: rank(records, 'automation_potential'), opportunity: rank(records, 'opportunity_score')},
      updated_at: new Date().toISOString()
    };
  }

  function uniqueLines(records, field, fallback) {
    const values = [...new Set(records.map(record => String(record[field] || '').trim()).filter(Boolean))].slice(0, 5);
    return values.length ? values.map(value => `- ${value}`).join('\n') : fallback;
  }

  function buildPrompt(theme, records) {
    const now = Date.now(), week = now - 7 * 86400000, month = now - 30 * 86400000;
    const scores = records.map(record => record.opportunity_score).filter(value => value != null);
    const average = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;
    const worth = average == null ? '待补充评分' : average >= 80 ? '高' : average >= 60 ? '中' : '低';
    const frequencies = [...new Set(records.map(record => record.repeatability).filter(Boolean))];
    const stats = {last_7_days: records.filter(r => new Date(r.occurred_at).getTime() >= week).length, last_30_days: records.filter(r => new Date(r.occurred_at).getTime() >= month).length, all_time: records.length, opportunity_score: average, worth_building: worth};
    const prompt = `我要开发一个“${theme.name}”工具。\n\n目前的问题：\n\n${theme.description?.trim() || '以下记录反映了同一个反复出现的需求。'}\n\n相关问题记录：\n\n${uniqueLines(records, 'problem', '尚未归入原始记录。')}\n\n出现次数：\n\n- 最近 7 天：${stats.last_7_days} 次\n- 最近 30 天：${stats.last_30_days} 次\n- 全部时间：${stats.all_time} 次\n\n目前流程：\n\n${uniqueLines(records, 'current_process', '尚未补充。')}\n\n存在的问题：\n\n${uniqueLines(records, 'pain_point', '尚未补充。')}\n\n当前解决方式及不足：\n\n${uniqueLines(records, 'current_solution', '尚未补充当前解决方式。')}\n${uniqueLines(records, 'solution_problem', '尚未补充当前方案的不足。')}\n\n希望实现：\n\n${uniqueLines(records, 'desired_state', '尚未补充理想状态。')}\n\n输入：\n\n${uniqueLines(records, 'input', '尚未明确。')}\n\n处理过程：\n\n根据上述流程和理想状态设计一个低摩擦、可维护的本地工具。\n\n输出：\n\n${uniqueLines(records, 'output', '尚未明确。')}\n\n使用频率：\n\n${frequencies.length ? frequencies.join(', ') : '尚未判断。'}\n\n项目价值评分：\n\n${average == null ? '待补充评分' : `${average} / 100`}\n\n是否值得开发：${worth}\n\n请先根据以上真实记录梳理最小可行范围，再分阶段实现；优先降低使用阻力，并确保数据可以完整导出。`;
    return {prompt, stats};
  }

  async function replaceTags(recordId, tagIds) {
    await checked(client.from('record_tags').delete().eq('record_id', recordId));
    if (tagIds?.length) await checked(client.from('record_tags').insert([...new Set(tagIds)].map(tag_id => ({record_id: recordId, tag_id}))));
  }

  async function request(rawUrl, options = {}) {
    const user = await requireUser();
    const url = new URL(rawUrl, location.origin), path = url.pathname, method = (options.method || 'GET').toUpperCase();
    const body = options.body ? JSON.parse(options.body) : {};

    if (path === '/api/health') {
      const { count } = await checked(client.from('records').select('id', {count: 'exact', head: true}));
      return {ok: true, phase: 9, schema_version: 1, records: count || 0, cloud: true};
    }
    if (path === '/api/tags' && method === 'GET') {
      const { data } = await checked(client.from('tags').select('id,name,category').order('category').order('id'));
      return {tags: data || []};
    }
    if (path === '/api/tags' && method === 'POST') {
      const name = String(body.name || '').trim();
      if (!name) throw new Error('请输入标签名称');
      const existing = await client.from('tags').select('id,name,category').eq('user_id', user.id).eq('name', name).eq('category', 'custom').maybeSingle();
      if (existing.error) throw new Error(existing.error.message);
      if (existing.data) return existing.data;
      const { data } = await checked(client.from('tags').insert({user_id: user.id, name, category: 'custom'}).select('id,name,category').single());
      return data;
    }
    if (path === '/api/records' && method === 'GET') {
      let records = await allRecords(true), q = (url.searchParams.get('q') || '').toLowerCase(), sort = url.searchParams.get('sort') || 'latest';
      if (q) records = records.filter(record => [record.context, record.problem, record.feeling_note].some(value => String(value || '').toLowerCase().includes(q)));
      const field = {pain: 'pain_score', frequency: 'frequency_score', time: 'time_cost_score', automation: 'automation_potential', opportunity: 'opportunity_score'}[sort];
      records.sort(sort === 'oldest' ? (a,b) => new Date(a.occurred_at)-new Date(b.occurred_at) : field ? (a,b) => (b[field] ?? -1)-(a[field] ?? -1) || new Date(b.occurred_at)-new Date(a.occurred_at) : (a,b) => new Date(b.occurred_at)-new Date(a.occurred_at));
      return {records};
    }
    if (path === '/api/records' && method === 'POST') {
      const feeling = Array.isArray(body.feeling) ? body.feeling : [];
      const payload = {user_id: user.id, context: String(body.context || '').trim(), problem: String(body.problem || '').trim(), original_context: String(body.context || '').trim(), original_problem: String(body.problem || '').trim(), original_feeling: feeling, feeling, feeling_note: String(body.feeling_note || '').trim(), scene: body.scene || '其他'};
      if (!payload.context || !payload.problem) throw new Error('请填写当时在做什么，以及发生了什么');
      const { data } = await checked(client.from('records').insert(payload).select('*').single());
      if (body.tag_ids?.length) await replaceTags(data.id, body.tag_ids);
      return (await recordsWithTags([data]))[0];
    }
    const recordMatch = path.match(/^\/api\/records\/(\d+)$/);
    if (recordMatch) {
      const id = Number(recordMatch[1]);
      if (method === 'GET') {
        const { data } = await checked(client.from('records').select('*').eq('id', id).single());
        return (await recordsWithTags([data]))[0];
      }
      if (method === 'DELETE') { await checked(client.from('records').delete().eq('id', id)); return null; }
      if (method === 'PUT') {
        const tagIds = body.tag_ids || [];
        const allowed = ['context','problem','feeling','feeling_note','scene','pain_score','frequency_score','time_cost_score','current_process','pain_point','current_solution','solution_problem','desired_state','input','output','repeatability','standardizable','automation_potential','usage_intent','related_need','status'];
        const payload = Object.fromEntries(allowed.filter(name => Object.hasOwn(body, name)).map(name => [name, body[name] === '' ? null : body[name]]));
        for (const name of ['feeling_note','current_process','pain_point','current_solution','solution_problem','desired_state','input','output']) if (payload[name] == null) payload[name] = '';
        const { data } = await checked(client.from('records').update(payload).eq('id', id).select('*').single());
        await replaceTags(id, tagIds);
        return (await recordsWithTags([data]))[0];
      }
    }
    if (path === '/api/themes' && method === 'GET') {
      const [{data: themeRows}, records] = await Promise.all([checked(client.from('themes').select('*').order('updated_at', {ascending:false})), allRecords(true)]);
      const themes = (themeRows || []).map(theme => {
        const linked = records.filter(record => record.related_need === theme.id), pains = linked.map(r => r.pain_score).filter(v => v != null), opportunities = linked.map(r => r.opportunity_score).filter(v => v != null);
        return {...theme, records: linked, record_count: linked.length, first_seen: linked.length ? linked.map(r => r.occurred_at).sort()[0] : null, last_seen: linked.length ? linked.map(r => r.occurred_at).sort().at(-1) : null, average_pain: pains.length ? Math.round(pains.reduce((a,b)=>a+b,0)/pains.length*10)/10 : null, opportunity_score: opportunities.length ? Math.round(opportunities.reduce((a,b)=>a+b,0)/opportunities.length) : null};
      });
      return {themes, unassigned_records: records.filter(record => record.related_need == null).length};
    }
    if (path === '/api/themes' && method === 'POST') {
      const { data } = await checked(client.from('themes').insert({user_id:user.id, name:String(body.name||'').trim(), description:String(body.description||'').trim()}).select('*').single());
      return data;
    }
    const themeMatch = path.match(/^\/api\/themes\/(\d+)$/);
    if (themeMatch && method === 'DELETE') { await checked(client.from('themes').delete().eq('id', Number(themeMatch[1]))); return null; }
    const promptMatch = path.match(/^\/api\/themes\/(\d+)\/prompt$/);
    if (promptMatch) {
      const id = Number(promptMatch[1]);
      const [{data: theme}, records] = await Promise.all([checked(client.from('themes').select('*').eq('id',id).single()), allRecords(true)]);
      const result = buildPrompt(theme, records.filter(record => record.related_need === id));
      return {theme_name: theme.name, ...result};
    }
    if (path === '/api/analytics') return analytics(await allRecords(false));
    if (path === '/api/review/weekly') {
      const now = new Date(), day = (now.getDay()+6)%7, start = new Date(now); start.setHours(0,0,0,0); start.setDate(start.getDate()-day); const end = new Date(start); end.setDate(end.getDate()+7);
      const records = (await allRecords(false)).filter(record => {const date=new Date(record.occurred_at); return date>=start && date<end;});
      const result = analytics(records);
      return {week:{start:start.toISOString().slice(0,10),end:new Date(end-1).toISOString().slice(0,10)},total_records:records.length,scene_counts:result.scene_counts,problem_tag_counts:result.problem_tag_counts,rankings:result.rankings};
    }
    if (path === '/api/export/json') {
      const [{data: themes}, {data: tags}, {data: recordTags}, records] = await Promise.all([checked(client.from('themes').select('*')), checked(client.from('tags').select('*')), checked(client.from('record_tags').select('*')), allRecords(true)]);
      return {exported_at:new Date().toISOString(),records,themes,tags,record_tags:recordTags};
    }
    if (path === '/api/export/csv') return allRecords(true);
    throw new Error('云端接口尚未支持此操作');
  }

  function download(name, content, type) {
    const url = URL.createObjectURL(new Blob([content], {type})), link = document.createElement('a');
    link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function csv(records) {
    const fields = ['id','context','problem','scene','feeling','feeling_note','pain_score','frequency_score','time_cost_score','automation_potential','usage_intent','opportunity_score','status','occurred_at','tags'];
    const quote = value => `"${String(value ?? '').replaceAll('"','""')}"`;
    return '\ufeff' + [fields.join(','), ...records.map(record => fields.map(field => quote(field === 'feeling' ? record.feeling.join(' | ') : field === 'tags' ? record.tags.map(tag=>tag.name).join(' | ') : record[field])).join(','))].join('\r\n');
  }

  function mountAuth() {
    const storageNote = document.querySelector('#storage-note');
    if (storageNote) storageNote.textContent = '数据保存在你的云端账号中，可在手机和电脑之间同步';
    document.head.insertAdjacentHTML('beforeend', `<style>.cloud-auth{position:fixed;inset:0;background:#f5f7f3;z-index:99;display:grid;place-items:center;padding:24px}.cloud-auth[hidden],.cloud-auth-card[hidden]{display:none}.cloud-auth-card{width:min(440px,100%);background:white;border:1px solid #dce4df;border-radius:20px;padding:30px;box-shadow:0 20px 60px rgba(33,53,45,.12)}.cloud-auth-card h1{font-size:32px}.cloud-auth-card input{width:100%;margin-top:8px;border:1px solid #ccd7d1;border-radius:11px;padding:12px 14px;color:#21352d;background:#fcfdfc;font:inherit;outline:none}.cloud-auth-card input:focus{border-color:#5f8775;box-shadow:0 0 0 3px #e5eee9}.cloud-auth-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:20px}.cloud-auth-link{appearance:none;border:0;background:none;color:#326b59;padding:8px 0;text-decoration:underline;cursor:pointer}.cloud-auth-message{min-height:24px;margin-top:14px;color:#a43b35}.cloud-auth-message[data-kind="success"]{color:#326b59}.cloud-user{font-size:12px;color:#6d7d75;display:flex;gap:8px;align-items:center;flex-wrap:wrap}.cloud-user button{padding:8px 10px}.cloud-delete-account{color:#a43b35}</style>`);
    document.body.insertAdjacentHTML('afterbegin', `<section id="cloud-auth" class="cloud-auth"><form id="cloud-auth-form" class="cloud-auth-card"><div class="eyebrow">Personal needs</div><h1>登录需求发现</h1><p>每个人只会看到自己的记录。</p><div class="field"><label class="legend" for="cloud-email">邮箱</label><input id="cloud-email" type="email" required autocomplete="email"></div><div class="field"><label class="legend" for="cloud-password">密码</label><input id="cloud-password" type="password" minlength="6" required autocomplete="current-password"></div><div class="cloud-auth-actions"><button type="submit">登录</button><button id="cloud-signup" type="button" class="secondary">注册</button><button id="cloud-forgot-password" type="button" class="cloud-auth-link">忘记密码</button></div><p id="cloud-auth-message" class="cloud-auth-message" role="status"></p></form><form id="cloud-reset-form" class="cloud-auth-card" hidden><div class="eyebrow">Personal needs</div><h1>设置新密码</h1><p>请输入至少 6 位的新密码。</p><div class="field"><label class="legend" for="cloud-new-password">新密码</label><input id="cloud-new-password" type="password" minlength="6" required autocomplete="new-password"></div><div class="field"><label class="legend" for="cloud-confirm-password">确认新密码</label><input id="cloud-confirm-password" type="password" minlength="6" required autocomplete="new-password"></div><div class="cloud-auth-actions"><button type="submit">保存新密码</button><button id="cloud-reset-cancel" type="button" class="secondary">取消</button></div><p id="cloud-reset-message" class="cloud-auth-message" role="status"></p></form></section>`);
    const gate = document.querySelector('#cloud-auth');
    const form = document.querySelector('#cloud-auth-form');
    const resetForm = document.querySelector('#cloud-reset-form');
    const message = document.querySelector('#cloud-auth-message');
    const resetMessage = document.querySelector('#cloud-reset-message');
    const emailInput = document.querySelector('#cloud-email');
    let resettingPassword = false;
    const authErrorMessage = error => ({
      anonymous_provider_disabled: '请先填写邮箱和密码，再点击注册。',
      email_address_not_authorized: '当前邮件服务不能向这个邮箱发送验证信，请联系管理员配置公共邮件服务。',
      email_not_confirmed: '邮箱尚未验证，请先打开验证邮件。',
      invalid_credentials: '邮箱或密码不正确。',
      email_exists: '这个邮箱已经注册，请直接登录。',
      user_already_exists: '这个邮箱已经注册，请直接登录。',
      weak_password: '密码强度不足，请换一个更安全的密码。'
    }[error.code] || error.message || '操作失败，请稍后重试。');
    const run = async signup => {
      if (!form.reportValidity()) {
        message.textContent = '请填写有效邮箱和至少 6 位密码。';
        return;
      }
      message.dataset.kind = '';
      message.textContent = signup ? '正在创建账号…' : '正在登录…';
      const email = emailInput.value.trim(), password = document.querySelector('#cloud-password').value;
      const result = signup
        ? await client.auth.signUp({email,password,options:{emailRedirectTo:location.origin}})
        : await client.auth.signInWithPassword({email,password});
      if (result.error) { message.textContent = authErrorMessage(result.error); return; }
      const obfuscatedExistingUser = signup && !result.data.session
        && Array.isArray(result.data.user?.identities) && result.data.user.identities.length === 0;
      if (obfuscatedExistingUser) {
        message.dataset.kind = '';
        message.textContent = '如果这个邮箱已经注册，请直接登录；如未注册，请打开验证邮件完成注册。';
        return;
      }
      message.dataset.kind = 'success';
      message.textContent = signup && !result.data.session ? '注册成功，请打开验证邮件后再登录。' : '';
    };
    form.addEventListener('submit', event => {event.preventDefault();run(false);});
    document.querySelector('#cloud-signup').addEventListener('click', () => run(true));
    document.querySelector('#cloud-forgot-password').addEventListener('click', async () => {
      if (!emailInput.reportValidity()) {
        message.textContent = '请先填写需要找回密码的邮箱。';
        return;
      }
      message.dataset.kind = '';
      message.textContent = '正在发送重置邮件…';
      const { error } = await client.auth.resetPasswordForEmail(emailInput.value.trim(), {redirectTo: `${location.origin}/?reset-password=1`});
      if (error) { message.textContent = authErrorMessage(error); return; }
      message.dataset.kind = 'success';
      message.textContent = '重置邮件已发送，请打开邮件中的链接。';
    });
    resetForm.addEventListener('submit', async event => {
      event.preventDefault();
      if (!resetForm.reportValidity()) return;
      const password = document.querySelector('#cloud-new-password').value;
      const confirmation = document.querySelector('#cloud-confirm-password').value;
      if (password !== confirmation) {
        resetMessage.textContent = '两次输入的密码不一致。';
        return;
      }
      resetMessage.dataset.kind = '';
      resetMessage.textContent = '正在更新密码…';
      const { error } = await client.auth.updateUser({password});
      if (error) { resetMessage.textContent = authErrorMessage(error); return; }
      resettingPassword = false;
      await client.auth.signOut();
      message.dataset.kind = 'success';
      message.textContent = '密码已更新，请使用新密码登录。';
    });
    document.querySelector('#cloud-reset-cancel').addEventListener('click', async () => {
      resettingPassword = false;
      await client.auth.signOut();
      render();
    });
    function render() {
      gate.hidden = Boolean(session) && !resettingPassword;
      form.hidden = resettingPassword;
      resetForm.hidden = !resettingPassword;
      document.querySelector('.cloud-user')?.remove();
      if (session && !resettingPassword) {
        const userBox = document.createElement('div'), email = document.createElement('span'), logout = document.createElement('button'), deleteAccount = document.createElement('button');
        userBox.className = 'cloud-user'; email.textContent = session.user.email || '已登录'; logout.type = 'button'; logout.className = 'secondary'; logout.textContent = '退出';
        deleteAccount.type = 'button'; deleteAccount.className = 'secondary cloud-delete-account'; deleteAccount.textContent = '注销账号';
        userBox.append(email, logout, deleteAccount); document.querySelector('header').append(userBox);
        logout.addEventListener('click', () => client.auth.signOut());
        deleteAccount.addEventListener('click', async () => {
          if (!confirm('确定永久注销账号吗？云端记录、主题和自定义标签都会删除，且无法恢复。建议先导出数据。')) return;
          deleteAccount.disabled = true;
          deleteAccount.textContent = '正在注销…';
          const { error } = await client.rpc('delete_own_account');
          if (error) {
            deleteAccount.disabled = false;
            deleteAccount.textContent = '注销账号';
            alert(`注销失败：${error.message}`);
            return;
          }
          await client.auth.signOut();
          message.dataset.kind = 'success';
          message.textContent = '账号及其云端数据已删除。';
        });
        window.dispatchEvent(new Event('cloud-auth-change'));
      }
    }
    client.auth.onAuthStateChange((event, next) => {
      session = next;
      if (event === 'PASSWORD_RECOVERY') resettingPassword = true;
      render();
    });
    client.auth.getSession().then(({data}) => {session = data.session; readyResolve(); render();});

    document.addEventListener('click', async event => {
      const link = event.target.closest('a[href^="/api/export/"]');
      if (!link) return;
      event.preventDefault();
      try {
        if (link.href.includes('/csv')) download('personal-needs.csv', csv(await request('/api/export/csv')), 'text/csv;charset=utf-8');
        else download('personal-needs.json', JSON.stringify(await request('/api/export/json'), null, 2), 'application/json');
      } catch (error) { alert(error.message); }
    });
    document.addEventListener('click', async event => {
      const link = event.target.closest('#download-prompt');
      if (!link) return;
      event.preventDefault();
      try { const data = await request(new URL(link.href).pathname); download(`${data.theme_name}.txt`, data.prompt, 'text/plain;charset=utf-8'); } catch(error) { alert(error.message); }
    });
  }

  window.CloudAPI = {enabled: true, request, client};
  mountAuth();
})();
