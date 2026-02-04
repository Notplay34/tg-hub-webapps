/**
 * Hub — Единое приложение
 */

const API_URL = window.API_URL || '';
const tg = window.Telegram?.WebApp;
let userId = 'anonymous';

if (tg) {
    tg.ready();
    tg.expand();
    if (tg.colorScheme === 'dark') document.body.classList.add('theme-dark');
    tg.setHeaderColor('secondary_bg_color');
    if (tg.initDataUnsafe?.user?.id) userId = String(tg.initDataUnsafe.user.id);
}

// === API ===
const API = {
    async request(method, endpoint, data = null) {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json', 'X-User-Id': userId }
        };
        if (data) options.body = JSON.stringify(data);
        const response = await fetch(API_URL + endpoint, options);
        if (!response.ok) throw new Error('API Error');
        return await response.json();
    }
};

// === Утилиты ===
const Utils = {
    today() { return new Date().toISOString().split('T')[0]; },
    
    weekFromNow() {
        const d = new Date();
        d.setDate(d.getDate() + 7);
        return d.toISOString().split('T')[0];
    },
    
    formatDate(str) {
        if (!str) return '';
        const today = this.today();
        if (str === today) return 'Сегодня';
        const d = new Date(str);
        return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
    },
    
    formatDateTime(str) {
        return new Date(str).toLocaleDateString('ru-RU', {
            day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
        });
    },
    
    escape(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
    
    initials(fio) {
        if (!fio) return '?';
        const parts = fio.split(' ').filter(p => p);
        return parts.length >= 2 ? (parts[0][0] + parts[1][0]).toUpperCase() : fio.substring(0, 2).toUpperCase();
    }
};

// === Навигация ===
const Nav = {
    init() {
        document.querySelectorAll('.nav-item').forEach(btn => {
            btn.addEventListener('click', () => this.goto(btn.dataset.screen));
        });
    },
    
    goto(screenId) {
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        
        document.getElementById(screenId).classList.add('active');
        document.querySelector(`[data-screen="${screenId}"]`).classList.add('active');
    }
};

// === Данные ===
let tasksData = [];
let peopleData = [];
let knowledgeData = [];

async function loadAllData() {
    try {
        [tasksData, peopleData, knowledgeData] = await Promise.all([
            API.request('GET', '/api/tasks'),
            API.request('GET', '/api/people'),
            API.request('GET', '/api/knowledge')
        ]);
    } catch (e) {
        console.error('Load error:', e);
    }
}

// === ЗАДАЧИ ===
const Tasks = {
    filter: 'all',
    
    async render() {
        const list = document.getElementById('tasksList');
        const empty = document.getElementById('tasksEmpty');
        
        let items = [...tasksData];
        const today = Utils.today();
        const week = Utils.weekFromNow();
        
        switch (this.filter) {
            case 'today': items = items.filter(t => !t.done && t.deadline === today); break;
            case 'week': items = items.filter(t => !t.done && t.deadline && t.deadline <= week); break;
            case 'done': items = items.filter(t => t.done); break;
            default: items = items.filter(t => !t.done);
        }
        
        if (items.length === 0) {
            list.innerHTML = '';
            empty.classList.add('show');
        } else {
            empty.classList.remove('show');
            list.innerHTML = items.map(t => this.renderItem(t)).join('');
        }
        
        this.updatePersonSelect();
    },
    
    renderItem(task) {
        const today = Utils.today();
        const deadlineClass = task.deadline ? (task.deadline < today ? 'overdue' : (task.deadline === today ? 'today' : '')) : '';
        const person = task.person_id ? peopleData.find(p => p.id === task.person_id) : null;
        
        return `
            <div class="card ${task.done ? 'done' : ''}" onclick="Tasks.openModal(${task.id})">
                <div class="card-header">
                    <div class="card-checkbox" onclick="event.stopPropagation();Tasks.toggle(${task.id})"></div>
                    <div class="card-body">
                        <div class="card-title">${Utils.escape(task.title)}</div>
                        ${task.description ? `<div class="card-desc">${Utils.escape(task.description)}</div>` : ''}
                        <div class="card-meta">
                            ${task.deadline ? `<span class="${deadlineClass}">📅 ${Utils.formatDate(task.deadline)}</span>` : ''}
                            <span class="priority-badge ${task.priority || 'medium'}">${{high:'Высокий',medium:'Средний',low:'Низкий'}[task.priority] || 'Средний'}</span>
                        </div>
                        ${person ? `<div class="linked-person"><span class="avatar small">${Utils.initials(person.fio)}</span>${Utils.escape(person.fio)}</div>` : ''}
                    </div>
                </div>
            </div>
        `;
    },
    
    updatePersonSelect() {
        const select = document.getElementById('taskPerson');
        select.innerHTML = '<option value="">— Не выбрано —</option>' + 
            peopleData.map(p => `<option value="${p.id}">${Utils.escape(p.fio)}</option>`).join('');
    },
    
    openModal(id = null) {
        const modal = document.getElementById('taskModal');
        const task = id ? tasksData.find(t => t.id === id) : null;
        
        document.getElementById('taskModalTitle').textContent = task ? 'Редактировать' : 'Новая задача';
        document.getElementById('taskId').value = task ? task.id : '';
        document.getElementById('taskTitle').value = task ? task.title : '';
        document.getElementById('taskDesc').value = task?.description || '';
        document.getElementById('taskDeadline').value = task?.deadline || Utils.today();
        document.getElementById('taskPriority').value = task?.priority || 'medium';
        document.getElementById('taskPerson').value = task?.person_id || '';
        document.getElementById('taskDelete').style.display = task ? 'block' : 'none';
        
        modal.classList.add('open');
    },
    
    closeModal() {
        document.getElementById('taskModal').classList.remove('open');
    },
    
    async save() {
        const id = document.getElementById('taskId').value;
        const data = {
            title: document.getElementById('taskTitle').value.trim(),
            description: document.getElementById('taskDesc').value.trim(),
            deadline: document.getElementById('taskDeadline').value || null,
            priority: document.getElementById('taskPriority').value,
            person_id: parseInt(document.getElementById('taskPerson').value) || null
        };
        
        if (!data.title) return alert('Введите название');
        
        try {
            if (id) {
                await API.request('PATCH', `/api/tasks/${id}`, data);
            } else {
                await API.request('POST', '/api/tasks', data);
            }
            this.closeModal();
            await loadAllData();
            this.render();
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        } catch (e) {
            alert('Ошибка сохранения');
        }
    },
    
    async toggle(id) {
        const task = tasksData.find(t => t.id === id);
        if (!task) return;
        
        try {
            await API.request('PATCH', `/api/tasks/${id}`, { done: !task.done });
            await loadAllData();
            this.render();
            if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
        } catch (e) {}
    },
    
    async delete() {
        const id = document.getElementById('taskId').value;
        if (!id) return;
        
        const doDelete = async () => {
            await API.request('DELETE', `/api/tasks/${id}`);
            this.closeModal();
            await loadAllData();
            this.render();
        };
        
        if (tg?.showConfirm) {
            tg.showConfirm('Удалить задачу?', ok => { if (ok) doDelete(); });
        } else if (confirm('Удалить?')) {
            doDelete();
        }
    },
    
    init() {
        document.querySelectorAll('#tasksFilters .filter').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#tasksFilters .filter').forEach(f => f.classList.remove('active'));
                btn.classList.add('active');
                this.filter = btn.dataset.filter;
                this.render();
            });
        });
    }
};

// === ЛЮДИ ===
const People = {
    currentId: null,
    editGroups: [],
    filter: 'all',
    
    async render() {
        const list = document.getElementById('peopleList');
        const empty = document.getElementById('peopleEmpty');
        const search = document.getElementById('peopleSearch').value.toLowerCase();
        
        let items = [...peopleData];
        
        if (search) {
            items = items.filter(p => p.fio.toLowerCase().includes(search));
        }
        
        if (this.filter !== 'all') {
            items = items.filter(p => p.data?.groups?.includes(this.filter));
        }
        
        if (items.length === 0) {
            list.innerHTML = '';
            empty.classList.add('show');
        } else {
            empty.classList.remove('show');
            list.innerHTML = items.map(p => this.renderItem(p)).join('');
        }
        
        this.renderFilters();
        this.updateSelects();
    },
    
    renderItem(person) {
        const data = person.data || {};
        return `
            <div class="person-item" onclick="People.openCard(${person.id})">
                <div class="avatar">${Utils.initials(person.fio)}</div>
                <div class="person-info">
                    <h3>${Utils.escape(person.fio)}</h3>
                    <p>${Utils.escape(data.relation || data.workplace || '')}</p>
                    ${data.groups?.length ? `<div class="card-tags">${data.groups.slice(0,3).map(g => `<span>${Utils.escape(g)}</span>`).join('')}</div>` : ''}
                </div>
            </div>
        `;
    },
    
    renderFilters() {
        const groups = new Set();
        peopleData.forEach(p => p.data?.groups?.forEach(g => groups.add(g)));
        
        const container = document.getElementById('peopleFilters');
        container.innerHTML = `<button class="filter ${this.filter === 'all' ? 'active' : ''}" data-filter="all">Все</button>` +
            Array.from(groups).sort().map(g => `<button class="filter ${this.filter === g ? 'active' : ''}" data-filter="${Utils.escape(g)}">${Utils.escape(g)}</button>`).join('');
        
        container.querySelectorAll('.filter').forEach(btn => {
            btn.addEventListener('click', () => {
                this.filter = btn.dataset.filter;
                this.render();
            });
        });
    },
    
    updateSelects() {
        const options = '<option value="">— Не выбрано —</option>' + 
            peopleData.map(p => `<option value="${p.id}">${Utils.escape(p.fio)}</option>`).join('');
        document.getElementById('taskPerson').innerHTML = options;
        document.getElementById('knowledgePerson').innerHTML = options;
    },
    
    openCard(id) {
        const person = peopleData.find(p => p.id === id);
        if (!person) return;
        
        this.currentId = id;
        document.getElementById('personName').textContent = person.fio;
        this.renderCard(person);
        
        Nav.goto('personScreen');
    },
    
    closeCard() {
        Nav.goto('peopleScreen');
        this.currentId = null;
    },
    
    renderCard(person) {
        const data = person.data || {};
        const tasks = tasksData.filter(t => t.person_id === person.id && !t.done);
        
        let html = `
            <div class="card-section">
                <h4>Основное</h4>
                ${this.field('Дата рождения', data.birth_date ? Utils.formatDate(data.birth_date) : null)}
                ${this.field('Кем приходится', data.relation)}
                ${this.field('Место работы', data.workplace)}
            </div>
            <div class="card-section">
                <h4>Характеристика</h4>
                ${this.field('Сильные стороны', data.strengths)}
                ${this.field('Слабые стороны', data.weaknesses)}
                ${this.field('Возможная польза', data.benefits)}
                ${this.field('Возможные проблемы', data.problems)}
            </div>
        `;
        
        if (data.groups?.length) {
            html += `<div class="card-section"><h4>Группы</h4><div class="card-tags">${data.groups.map(g => `<span>${Utils.escape(g)}</span>`).join('')}</div></div>`;
        }
        
        if (tasks.length) {
            html += `<div class="card-section"><h4>Активные задачи</h4>${tasks.map(t => `<div class="card" onclick="Tasks.openModal(${t.id})"><div class="card-title">${Utils.escape(t.title)}</div></div>`).join('')}</div>`;
        }
        
        html += `
            <div class="card-section">
                <div class="notes-header">
                    <h4>Заметки</h4>
                    <button class="btn-add-note" onclick="People.openNoteModal()">+ Добавить</button>
                </div>
                ${person.notes?.length ? person.notes.map(n => `
                    <div class="note-item">
                        <div class="note-date">${Utils.formatDateTime(n.created_at)}</div>
                        <div class="note-text">${Utils.escape(n.text)}</div>
                        <button class="note-delete" onclick="People.deleteNote(${n.id})">Удалить</button>
                    </div>
                `).join('') : '<p class="card-field"><p class="empty">Нет заметок</p></p>'}
            </div>
        `;
        
        document.getElementById('personCard').innerHTML = html;
    },
    
    field(label, value) {
        return `<div class="card-field"><label>${label}</label><p class="${value ? '' : 'empty'}">${Utils.escape(value) || '—'}</p></div>`;
    },
    
    openModal(id = null) {
        const person = id ? peopleData.find(p => p.id === id) : null;
        const data = person?.data || {};
        
        document.getElementById('personModalTitle').textContent = person ? 'Редактировать' : 'Новый контакт';
        document.getElementById('personId').value = person ? person.id : '';
        document.getElementById('personFio').value = person?.fio || '';
        document.getElementById('personBirth').value = data.birth_date || '';
        document.getElementById('personRelation').value = data.relation || '';
        document.getElementById('personWork').value = data.workplace || '';
        document.getElementById('personStrengths').value = data.strengths || '';
        document.getElementById('personWeaknesses').value = data.weaknesses || '';
        document.getElementById('personBenefits').value = data.benefits || '';
        document.getElementById('personProblems').value = data.problems || '';
        
        this.editGroups = data.groups ? [...data.groups] : [];
        this.renderGroups();
        
        document.getElementById('personDelete').style.display = person ? 'block' : 'none';
        document.getElementById('personModal').classList.add('open');
    },
    
    closeModal() {
        document.getElementById('personModal').classList.remove('open');
    },
    
    edit() {
        this.openModal(this.currentId);
    },
    
    renderGroups() {
        document.getElementById('personGroupsList').innerHTML = this.editGroups.map(g => 
            `<span class="tag">${Utils.escape(g)}<span class="tag-remove" onclick="People.removeGroup('${Utils.escape(g)}')">&times;</span></span>`
        ).join('');
    },
    
    addGroup() {
        const input = document.getElementById('personGroupInput');
        const val = input.value.trim();
        if (val && !this.editGroups.includes(val)) {
            this.editGroups.push(val);
            this.renderGroups();
        }
        input.value = '';
    },
    
    removeGroup(g) {
        this.editGroups = this.editGroups.filter(x => x !== g);
        this.renderGroups();
    },
    
    async save() {
        const id = document.getElementById('personId').value;
        const data = {
            fio: document.getElementById('personFio').value.trim(),
            birth_date: document.getElementById('personBirth').value || null,
            relation: document.getElementById('personRelation').value.trim() || null,
            workplace: document.getElementById('personWork').value.trim() || null,
            strengths: document.getElementById('personStrengths').value.trim() || null,
            weaknesses: document.getElementById('personWeaknesses').value.trim() || null,
            benefits: document.getElementById('personBenefits').value.trim() || null,
            problems: document.getElementById('personProblems').value.trim() || null,
            groups: this.editGroups,
            connections: []
        };
        
        if (!data.fio) return alert('Введите ФИО');
        
        try {
            if (id) {
                await API.request('PATCH', `/api/people/${id}`, data);
            } else {
                const result = await API.request('POST', '/api/people', data);
                this.currentId = result.id;
            }
            this.closeModal();
            await loadAllData();
            this.render();
            
            if (this.currentId) {
                const person = peopleData.find(p => p.id === this.currentId);
                if (person) {
                    document.getElementById('personName').textContent = person.fio;
                    this.renderCard(person);
                }
            }
            
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        } catch (e) {
            alert('Ошибка сохранения');
        }
    },
    
    async delete() {
        const id = document.getElementById('personId').value;
        if (!id) return;
        
        const doDelete = async () => {
            await API.request('DELETE', `/api/people/${id}`);
            this.closeModal();
            this.closeCard();
            await loadAllData();
            this.render();
        };
        
        if (tg?.showConfirm) {
            tg.showConfirm('Удалить контакт?', ok => { if (ok) doDelete(); });
        } else if (confirm('Удалить?')) {
            doDelete();
        }
    },
    
    openNoteModal() {
        document.getElementById('noteText').value = '';
        document.getElementById('noteModal').classList.add('open');
    },
    
    closeNoteModal() {
        document.getElementById('noteModal').classList.remove('open');
    },
    
    async saveNote() {
        const text = document.getElementById('noteText').value.trim();
        if (!text) return;
        
        try {
            await API.request('POST', `/api/people/${this.currentId}/notes`, { text });
            this.closeNoteModal();
            await loadAllData();
            const person = peopleData.find(p => p.id === this.currentId);
            if (person) this.renderCard(person);
        } catch (e) {}
    },
    
    async deleteNote(noteId) {
        const doDelete = async () => {
            await API.request('DELETE', `/api/people/${this.currentId}/notes/${noteId}`);
            await loadAllData();
            const person = peopleData.find(p => p.id === this.currentId);
            if (person) this.renderCard(person);
        };
        
        if (tg?.showConfirm) {
            tg.showConfirm('Удалить заметку?', ok => { if (ok) doDelete(); });
        } else if (confirm('Удалить?')) {
            doDelete();
        }
    }
};

// === БАЗА ЗНАНИЙ ===
const Knowledge = {
    currentId: null,
    editTags: [],
    filter: 'all',
    
    async render() {
        const list = document.getElementById('knowledgeList');
        const empty = document.getElementById('knowledgeEmpty');
        const search = document.getElementById('knowledgeSearch').value.toLowerCase();
        
        let items = [...knowledgeData];
        
        if (search) {
            items = items.filter(k => k.title.toLowerCase().includes(search) || k.content?.toLowerCase().includes(search));
        }
        
        if (this.filter !== 'all') {
            items = items.filter(k => k.tags?.includes(this.filter));
        }
        
        if (items.length === 0) {
            list.innerHTML = '';
            empty.classList.add('show');
        } else {
            empty.classList.remove('show');
            list.innerHTML = items.map(k => this.renderItem(k)).join('');
        }
        
        this.renderFilters();
    },
    
    renderItem(item) {
        const person = item.person_id ? peopleData.find(p => p.id === item.person_id) : null;
        
        return `
            <div class="card" onclick="Knowledge.view(${item.id})">
                <div class="card-title">${Utils.escape(item.title)}</div>
                ${item.content ? `<div class="card-desc">${Utils.escape(item.content)}</div>` : ''}
                ${item.tags?.length ? `<div class="card-tags">${item.tags.map(t => `<span>${Utils.escape(t)}</span>`).join('')}</div>` : ''}
                ${person ? `<div class="linked-person"><span class="avatar small">${Utils.initials(person.fio)}</span>${Utils.escape(person.fio)}</div>` : ''}
            </div>
        `;
    },
    
    renderFilters() {
        const tags = new Set();
        knowledgeData.forEach(k => k.tags?.forEach(t => tags.add(t)));
        
        const container = document.getElementById('knowledgeFilters');
        container.innerHTML = `<button class="filter ${this.filter === 'all' ? 'active' : ''}" data-filter="all">Все</button>` +
            Array.from(tags).sort().map(t => `<button class="filter ${this.filter === t ? 'active' : ''}" data-filter="${Utils.escape(t)}">${Utils.escape(t)}</button>`).join('');
        
        container.querySelectorAll('.filter').forEach(btn => {
            btn.addEventListener('click', () => {
                this.filter = btn.dataset.filter;
                this.render();
            });
        });
    },
    
    view(id) {
        const item = knowledgeData.find(k => k.id === id);
        if (!item) return;
        
        this.currentId = id;
        document.getElementById('knowledgeViewTitle').textContent = item.title;
        document.getElementById('knowledgeViewContent').textContent = item.content || '';
        
        let meta = '';
        if (item.tags?.length) {
            meta += `<div class="tags">${item.tags.map(t => `<span>${Utils.escape(t)}</span>`).join('')}</div>`;
        }
        meta += Utils.formatDateTime(item.created_at);
        document.getElementById('knowledgeViewMeta').innerHTML = meta;
        
        document.getElementById('knowledgeViewModal').classList.add('open');
    },
    
    closeView() {
        document.getElementById('knowledgeViewModal').classList.remove('open');
        this.currentId = null;
    },
    
    editCurrent() {
        this.closeView();
        this.openModal(this.currentId);
    },
    
    openModal(id = null) {
        const item = id ? knowledgeData.find(k => k.id === id) : null;
        
        document.getElementById('knowledgeModalTitle').textContent = item ? 'Редактировать' : 'Новая запись';
        document.getElementById('knowledgeId').value = item ? item.id : '';
        document.getElementById('knowledgeTitle').value = item?.title || '';
        document.getElementById('knowledgeContent').value = item?.content || '';
        document.getElementById('knowledgePerson').value = item?.person_id || '';
        
        this.editTags = item?.tags ? [...item.tags] : [];
        this.renderTags();
        
        document.getElementById('knowledgeDelete').style.display = item ? 'block' : 'none';
        document.getElementById('knowledgeModal').classList.add('open');
    },
    
    closeModal() {
        document.getElementById('knowledgeModal').classList.remove('open');
    },
    
    renderTags() {
        document.getElementById('knowledgeTagsList').innerHTML = this.editTags.map(t => 
            `<span class="tag">${Utils.escape(t)}<span class="tag-remove" onclick="Knowledge.removeTag('${Utils.escape(t)}')">&times;</span></span>`
        ).join('');
    },
    
    addTag() {
        const input = document.getElementById('knowledgeTagInput');
        const val = input.value.trim();
        if (val && !this.editTags.includes(val)) {
            this.editTags.push(val);
            this.renderTags();
        }
        input.value = '';
    },
    
    removeTag(t) {
        this.editTags = this.editTags.filter(x => x !== t);
        this.renderTags();
    },
    
    async save() {
        const id = document.getElementById('knowledgeId').value;
        const data = {
            title: document.getElementById('knowledgeTitle').value.trim(),
            content: document.getElementById('knowledgeContent').value.trim(),
            tags: this.editTags,
            person_id: parseInt(document.getElementById('knowledgePerson').value) || null
        };
        
        if (!data.title) return alert('Введите заголовок');
        
        try {
            if (id) {
                await API.request('PATCH', `/api/knowledge/${id}`, data);
            } else {
                await API.request('POST', '/api/knowledge', data);
            }
            this.closeModal();
            await loadAllData();
            this.render();
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        } catch (e) {
            alert('Ошибка сохранения');
        }
    },
    
    async delete() {
        const id = document.getElementById('knowledgeId').value;
        if (!id) return;
        
        const doDelete = async () => {
            await API.request('DELETE', `/api/knowledge/${id}`);
            this.closeModal();
            await loadAllData();
            this.render();
        };
        
        if (tg?.showConfirm) {
            tg.showConfirm('Удалить запись?', ok => { if (ok) doDelete(); });
        } else if (confirm('Удалить?')) {
            doDelete();
        }
    }
};

// === ИИ (заглушка) ===
const AI = {
    send() {
        const input = document.getElementById('chatInput');
        const text = input.value.trim();
        if (!text) return;
        
        const messages = document.getElementById('chatMessages');
        messages.innerHTML += `<div class="chat-msg user">${Utils.escape(text)}</div>`;
        input.value = '';
        
        // Заглушка ответа
        setTimeout(() => {
            messages.innerHTML += `<div class="chat-msg ai">ИИ-ассистент будет подключен в следующем обновлении. Пока я могу показать статистику:\n\n📋 Задач: ${tasksData.filter(t => !t.done).length} активных\n👤 Людей: ${peopleData.length}\n📚 Записей: ${knowledgeData.length}</div>`;
            messages.scrollTop = messages.scrollHeight;
        }, 500);
    }
};

// === ИНИЦИАЛИЗАЦИЯ ===
async function init() {
    Nav.init();
    Tasks.init();
    
    await loadAllData();
    Tasks.render();
    People.render();
    Knowledge.render();
    
    // Закрытие модалов
    document.querySelectorAll('.modal').forEach(m => {
        m.addEventListener('click', e => {
            if (e.target === m) m.classList.remove('open');
        });
    });
}

init();
