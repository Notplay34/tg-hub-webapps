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
        
        try {
            const url = API_URL + endpoint;
            console.log(`API Request: ${method} ${url}`, data);
            
            const response = await fetch(url, options);
            
            if (!response.ok) {
                let errorText = '';
                try {
                    const errorData = await response.json();
                    errorText = errorData.detail || errorData.message || JSON.stringify(errorData);
                } catch {
                    errorText = await response.text();
                }
                throw new Error(`HTTP ${response.status}: ${errorText || 'Ошибка сервера'}`);
            }
            
            const result = await response.json();
            console.log(`API Response:`, result);
            return result;
        } catch (e) {
            console.error('API Error:', e);
            if (e.name === 'TypeError' && e.message.includes('fetch')) {
                throw new Error(`Нет соединения с сервером. Проверьте URL: ${API_URL}`);
            }
            throw e;
        }
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
        
        const screen = document.getElementById(screenId);
        if (screen) {
            screen.classList.add('active');
            const navBtn = document.querySelector(`[data-screen="${screenId}"]`);
            if (navBtn) navBtn.classList.add('active');
            
            // Обновляем экраны при переходе
            if (screenId === 'statsScreen') {
                Today.render();
            } else if (screenId === 'timelineScreen') {
                Timeline.load();
            }
        }
    }
};

// === Данные ===
let tasksData = [];
let peopleData = [];
let knowledgeData = [];

async function loadAllData(showLoading = true) {
    if (showLoading) {
        showLoadingState('tasks');
        showLoadingState('people');
        showLoadingState('knowledge');
    }
    
    try {
        [tasksData, peopleData, knowledgeData] = await Promise.all([
            API.request('GET', '/api/tasks'),
            API.request('GET', '/api/people'),
            API.request('GET', '/api/knowledge')
        ]);
        
        hideLoadingState('tasks');
        hideLoadingState('people');
        hideLoadingState('knowledge');
        hideErrorState('tasks');
        hideErrorState('people');
        hideErrorState('knowledge');
        
        // Обновляем главный экран
        Today.render();
    } catch (e) {
        console.error('Load error:', e);
        hideLoadingState('tasks');
        hideLoadingState('people');
        hideLoadingState('knowledge');
        showErrorState('tasks', e.message);
        showErrorState('people', e.message);
        showErrorState('knowledge', e.message);
    }
}

function showLoadingState(module) {
    const el = document.getElementById(`${module}Loading`);
    if (el) {
        const list = document.getElementById(`${module}List`);
        if (list) list.style.display = 'none';
        const content = document.getElementById(`${module}Content`);
        if (content) content.style.display = 'none';
        document.getElementById(`${module}Empty`).classList.remove('show');
        document.getElementById(`${module}Error`).classList.remove('show');
        el.classList.add('show');
    }
}

function hideLoadingState(module) {
    const el = document.getElementById(`${module}Loading`);
    if (el) el.classList.remove('show');
    const list = document.getElementById(`${module}List`);
    if (list) {
        list.style.display = 'block';
        const content = document.getElementById(`${module}Content`);
        if (content) content.style.display = 'block';
    }
}

function showErrorState(module, message) {
    const el = document.getElementById(`${module}Error`);
    if (el) {
        el.querySelector('p').textContent = `❌ ${message}`;
        el.classList.add('show');
    }
}

function hideErrorState(module) {
    const el = document.getElementById(`${module}Error`);
    if (el) el.classList.remove('show');
}

// === ГЛАВНЫЙ ЭКРАН (ЗАДАЧИ НА СЕГОДНЯ) ===
const Today = {
    async render() {
        const list = document.getElementById('todayList');
        const empty = document.getElementById('todayEmpty');
        
        const today = Utils.today();
        const items = tasksData.filter(t => !t.done && t.deadline === today);
        
        if (items.length === 0) {
            list.innerHTML = '';
            empty.classList.add('show');
        } else {
            empty.classList.remove('show');
            list.innerHTML = items.map(t => Tasks.renderItem(t)).join('');
            Tasks.initSwipe();
        }
    }
};

// === ГЛОБАЛЬНЫЙ ПОИСК ===
const GlobalSearch = {
    open() {
        Nav.goto('searchScreen');
        document.getElementById('globalSearchInput').focus();
    },
    
    close() {
        document.getElementById('globalSearchInput').value = '';
        Nav.goto('statsScreen');
    },
    
    search() {
        const query = document.getElementById('globalSearchInput').value.toLowerCase().trim();
        const results = document.getElementById('searchResults');
        
        if (!query) {
            results.innerHTML = `
                <div class="search-placeholder">
                    <div class="search-placeholder-icon">🔍</div>
                    <p>Введите запрос для поиска</p>
                </div>
            `;
            return;
        }
        
        let allResults = [];
        
        // Поиск в задачах
        tasksData.forEach(t => {
            if (t.title.toLowerCase().includes(query) || t.description?.toLowerCase().includes(query)) {
                allResults.push({
                    type: 'task',
                    id: t.id,
                    title: t.title,
                    desc: t.description || '',
                    icon: '📋',
                    action: () => { Nav.goto('tasksScreen'); Tasks.openModal(t.id); }
                });
            }
        });
        
        // Поиск в людях
        peopleData.forEach(p => {
            const data = p.data || {};
            if (p.fio.toLowerCase().includes(query) || 
                data.relation?.toLowerCase().includes(query) ||
                data.workplace?.toLowerCase().includes(query)) {
                allResults.push({
                    type: 'person',
                    id: p.id,
                    title: p.fio,
                    desc: data.relation || data.workplace || '',
                    icon: '👤',
                    action: () => { Nav.goto('peopleScreen'); People.openCard(p.id); }
                });
            }
        });
        
        // Поиск в знаниях
        knowledgeData.forEach(k => {
            if (k.title.toLowerCase().includes(query) || k.content?.toLowerCase().includes(query)) {
                allResults.push({
                    type: 'knowledge',
                    id: k.id,
                    title: k.title,
                    desc: k.content?.substring(0, 100) || '',
                    icon: '📚',
                    action: () => { Nav.goto('knowledgeScreen'); Knowledge.view(k.id); }
                });
            }
        });
        
        if (allResults.length === 0) {
            results.innerHTML = `
                <div class="search-placeholder">
                    <div class="search-placeholder-icon">🔍</div>
                    <p>Ничего не найдено</p>
                </div>
            `;
        } else {
            results.innerHTML = allResults.map(r => `
                <div class="search-result-item" data-type="${r.type}" onclick="GlobalSearch.select(${r.id}, '${r.type}')">
                    <div class="search-result-header">
                        <span class="search-result-type">${r.type === 'task' ? 'Задача' : (r.type === 'person' ? 'Человек' : 'Знание')}</span>
                    </div>
                    <div class="search-result-title">${Utils.escape(r.title)}</div>
                    ${r.desc ? `<div class="search-result-desc">${Utils.escape(r.desc)}</div>` : ''}
                </div>
            `).join('');
        }
    },
    
    select(id, type) {
        this.close();
        setTimeout(() => {
            if (type === 'task') Tasks.openModal(id);
            else if (type === 'person') People.openCard(id);
            else if (type === 'knowledge') Knowledge.view(id);
        }, 300);
    }
};

// === ЗАДАЧИ ===
const Tasks = {
    filter: 'all',
    sortBy: 'date', // date, priority, title
    
    async render() {
        const list = document.getElementById('tasksList');
        const empty = document.getElementById('tasksEmpty');
        
        hideLoadingState('tasks');
        hideErrorState('tasks');
        
        let items = [...tasksData];
        const today = Utils.today();
        const week = Utils.weekFromNow();
        
        switch (this.filter) {
            case 'today': items = items.filter(t => !t.done && t.deadline === today); break;
            case 'week': items = items.filter(t => !t.done && t.deadline && t.deadline <= week); break;
            case 'done': items = items.filter(t => t.done); break;
            default: items = items.filter(t => !t.done);
        }
        
        // Сортировка
        items.sort((a, b) => {
            if (this.sortBy === 'priority') {
                const priorityOrder = {high: 3, medium: 2, low: 1};
                return (priorityOrder[b.priority] || 2) - (priorityOrder[a.priority] || 2);
            } else if (this.sortBy === 'title') {
                return a.title.localeCompare(b.title, 'ru');
            } else { // date
                if (!a.deadline && !b.deadline) return 0;
                if (!a.deadline) return 1;
                if (!b.deadline) return -1;
                return a.deadline.localeCompare(b.deadline);
            }
        });
        
        if (items.length === 0) {
            list.innerHTML = '';
            empty.classList.add('show');
        } else {
            empty.classList.remove('show');
            list.innerHTML = items.map(t => this.renderItem(t)).join('');
            this.initSwipe();
        }
        
        this.updatePersonSelect();
        this.updateSortLabel();
    },
    
    toggleSort() {
        const sorts = ['date', 'priority', 'title'];
        const currentIndex = sorts.indexOf(this.sortBy);
        this.sortBy = sorts[(currentIndex + 1) % sorts.length];
        this.render();
    },
    
    updateSortLabel() {
        const labels = {date: 'По дате', priority: 'По приоритету', title: 'По названию'};
        document.getElementById('tasksSortLabel').textContent = labels[this.sortBy];
    },
    
    initSwipe() {
        document.querySelectorAll('#tasksList .card').forEach(card => {
            let startX = 0;
            let currentX = 0;
            let isSwiping = false;
            
            card.addEventListener('touchstart', (e) => {
                startX = e.touches[0].clientX;
                isSwiping = true;
            });
            
            card.addEventListener('touchmove', (e) => {
                if (!isSwiping) return;
                currentX = e.touches[0].clientX - startX;
                if (currentX < 0) {
                    card.style.transform = `translateX(${currentX}px)`;
                    card.classList.add('swiping');
                }
            });
            
            card.addEventListener('touchend', () => {
                if (currentX < -80) {
                    card.classList.add('swiped');
                    const taskId = parseInt(card.getAttribute('data-task-id'));
                    setTimeout(() => {
                        this.delete(taskId);
                    }, 200);
                } else {
                    card.style.transform = '';
                    card.classList.remove('swiping', 'swiped');
                }
                isSwiping = false;
                currentX = 0;
            });
        });
    },
    
    renderItem(task) {
        const today = Utils.today();
        const deadlineClass = task.deadline ? (task.deadline < today ? 'overdue' : (task.deadline === today ? 'today' : '')) : '';
        const person = task.person_id ? peopleData.find(p => p.id === task.person_id) : null;
        
        const priorityIcons = {
            high: '🔴',
            medium: '🟡',
            low: '🟢'
        };
        
        const statusIcon = task.done ? '✅' : (task.deadline && task.deadline < today ? '⏰' : '📋');
        
        return `
            <div class="card ${task.done ? 'done' : ''}" data-task-id="${task.id}" onclick="Tasks.openModal(${task.id})">
                <button class="card-delete" onclick="event.stopPropagation();Tasks.delete(${task.id})" title="Удалить">×</button>
                <div class="card-actions">
                    <button class="card-action-btn" onclick="event.stopPropagation();Tasks.delete(${task.id})">🗑</button>
                </div>
                <div class="card-header">
                    <div class="card-checkbox" onclick="event.stopPropagation();Tasks.toggle(${task.id})"></div>
                    <div class="card-body" style="flex:1">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                            <span style="font-size:18px">${statusIcon}</span>
                            <div class="card-title" style="flex:1;margin:0">${Utils.escape(task.title)}</div>
                        </div>
                        ${task.description ? `<div class="card-desc">${Utils.escape(task.description)}</div>` : ''}
                        <div class="card-meta">
                            <span class="priority-badge ${task.priority || 'medium'}">
                                ${priorityIcons[task.priority] || '🟡'} ${task.priority === 'high' ? 'Высокий' : (task.priority === 'low' ? 'Низкий' : 'Средний')}
                            </span>
                            ${task.deadline ? `<span class="${deadlineClass}">📅 ${Utils.formatDate(task.deadline)}</span>` : ''}
                        </div>
                        ${person ? `<div class="linked-person" style="margin-top:8px"><span class="avatar small">${Utils.initials(person.fio)}</span>${Utils.escape(person.fio)}</div>` : ''}
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
            console.error('Save error:', e);
            const errorMsg = e.message || 'Ошибка сохранения';
            if (tg?.showAlert) {
                tg.showAlert(`Ошибка: ${errorMsg}`);
            } else {
                alert(`Ошибка сохранения: ${errorMsg}`);
            }
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
    
    async delete(id = null) {
        const taskId = id || document.getElementById('taskId').value;
        if (!taskId) return;
        
        const doDelete = async () => {
            await API.request('DELETE', `/api/tasks/${taskId}`);
            if (!id) this.closeModal();
            await loadAllData();
            this.render();
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        };
        
        if (tg?.showConfirm) {
            tg.showConfirm('Удалить задачу?', ok => { if (ok) doDelete(); });
        } else if (confirm('Удалить задачу?')) {
            doDelete();
        }
    },
    
    async retry() {
        await loadAllData();
        this.render();
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
        
        hideLoadingState('people');
        hideErrorState('people');
        
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
            <div class="person-item" onclick="People.openCard(${person.id})" style="position:relative">
                <button class="card-delete" onclick="event.stopPropagation();People.delete(${person.id})" title="Удалить" style="position:absolute;top:12px;right:12px">×</button>
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
            html += `
                <div class="card-section">
                    <h4>Активные задачи (${tasks.length})</h4>
                    ${tasks.map(t => {
                        const today = Utils.today();
                        const deadlineClass = t.deadline ? (t.deadline < today ? 'overdue' : (t.deadline === today ? 'today' : '')) : '';
                        return `
                            <div class="card linked-task" onclick="Nav.goto('tasksScreen');Tasks.openModal(${t.id})" style="margin-bottom:8px;cursor:pointer">
                                <div style="display:flex;align-items:center;gap:8px">
                                    <span style="font-size:16px">${t.done ? '✅' : '📋'}</span>
                                    <div style="flex:1">
                                        <div class="card-title" style="margin:0;font-size:15px">${Utils.escape(t.title)}</div>
                                        ${t.deadline ? `<div style="font-size:12px;color:var(--text-secondary);margin-top:4px" class="${deadlineClass}">📅 ${Utils.formatDate(t.deadline)}</div>` : ''}
                                    </div>
                                    <span style="color:var(--accent);font-size:18px">→</span>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        }
        
        // Связанные знания
        const relatedKnowledge = knowledgeData.filter(k => k.person_id === person.id);
        if (relatedKnowledge.length) {
            html += `
                <div class="card-section">
                    <h4>Связанные записи (${relatedKnowledge.length})</h4>
                    ${relatedKnowledge.map(k => `
                        <div class="card linked-knowledge" onclick="Nav.goto('knowledgeScreen');Knowledge.view(${k.id})" style="margin-bottom:8px;cursor:pointer">
                            <div style="display:flex;align-items:center;gap:8px">
                                <span style="font-size:16px">📚</span>
                                <div style="flex:1">
                                    <div class="card-title" style="margin:0;font-size:15px">${Utils.escape(k.title)}</div>
                                    ${k.content ? `<div style="font-size:12px;color:var(--text-secondary);margin-top:4px">${Utils.escape(k.content.substring(0, 60))}${k.content.length > 60 ? '...' : ''}</div>` : ''}
                                </div>
                                <span style="color:var(--accent);font-size:18px">→</span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
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
            console.error('Save error:', e);
            const errorMsg = e.message || 'Ошибка сохранения';
            if (tg?.showAlert) {
                tg.showAlert(`Ошибка: ${errorMsg}`);
            } else {
                alert(`Ошибка сохранения: ${errorMsg}`);
            }
        }
    },
    
    async delete(id = null) {
        const personId = id || document.getElementById('personId').value;
        if (!personId) return;
        
        const doDelete = async () => {
            await API.request('DELETE', `/api/people/${personId}`);
            if (!id) {
                this.closeModal();
                this.closeCard();
            }
            await loadAllData();
            this.render();
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        };
        
        if (tg?.showConfirm) {
            tg.showConfirm('Удалить контакт?', ok => { if (ok) doDelete(); });
        } else if (confirm('Удалить контакт?')) {
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
    },
    
    async retry() {
        await loadAllData();
        this.render();
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
        
        hideLoadingState('knowledge');
        hideErrorState('knowledge');
        
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
                <button class="card-delete" onclick="event.stopPropagation();Knowledge.delete(${item.id})" title="Удалить">×</button>
                <div class="card-title">${Utils.escape(item.title)}</div>
                ${item.content ? `<div class="card-desc">${Utils.escape(item.content)}</div>` : ''}
                ${item.tags?.length ? `<div class="card-tags">${item.tags.map(t => `<span>${Utils.escape(t)}</span>`).join('')}</div>` : ''}
                        ${person ? `
                            <div class="linked-person" onclick="event.stopPropagation();People.openCard(${person.id})" style="cursor:pointer;margin-top:8px">
                                <span class="avatar small">${Utils.initials(person.fio)}</span>
                                <span style="font-weight:500">${Utils.escape(person.fio)}</span>
                                <span style="margin-left:auto;color:var(--accent);font-size:12px">→</span>
                            </div>
                        ` : ''}
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
        
        const person = item.person_id ? peopleData.find(p => p.id === item.person_id) : null;
        
        let meta = '';
        if (person) {
            meta += `
                <div class="linked-person-view" onclick="People.openCard(${person.id})" style="cursor:pointer;padding:12px;background:var(--bg-secondary);border-radius:12px;margin-bottom:12px;display:flex;align-items:center;gap:12px">
                    <span class="avatar">${Utils.initials(person.fio)}</span>
                    <div style="flex:1">
                        <div style="font-weight:600;font-size:14px">${Utils.escape(person.fio)}</div>
                        <div style="font-size:12px;color:var(--text-secondary)">Связанный человек</div>
                    </div>
                    <span style="color:var(--accent);font-size:20px">→</span>
                </div>
            `;
        }
        if (item.tags?.length) {
            meta += `<div class="tags">${item.tags.map(t => `<span>${Utils.escape(t)}</span>`).join('')}</div>`;
        }
        meta += `<div style="margin-top:12px;font-size:12px;color:var(--text-secondary)">${Utils.formatDateTime(item.created_at)}</div>`;
        document.getElementById('knowledgeViewMeta').innerHTML = meta;
        
        document.getElementById('knowledgeViewModal').classList.add('open');
    },
    
    closeView() {
        document.getElementById('knowledgeViewModal').classList.remove('open');
        this.currentId = null;
    },
    
    editCurrent() {
        const id = this.currentId; // Сохраняем ID перед закрытием
        if (!id) return;
        document.getElementById('knowledgeViewModal').classList.remove('open');
        this.openModal(id); // Используем сохранённый ID
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
            console.error('Save error:', e);
            const errorMsg = e.message || 'Ошибка сохранения';
            if (tg?.showAlert) {
                tg.showAlert(`Ошибка: ${errorMsg}`);
            } else {
                alert(`Ошибка сохранения: ${errorMsg}`);
            }
        }
    },
    
    async delete(id = null) {
        const itemId = id || document.getElementById('knowledgeId').value;
        if (!itemId) return;
        
        const doDelete = async () => {
            await API.request('DELETE', `/api/knowledge/${itemId}`);
            if (!id) this.closeModal();
            await loadAllData();
            this.render();
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        };
        
        if (tg?.showConfirm) {
            tg.showConfirm('Удалить запись?', ok => { if (ok) doDelete(); });
        } else if (confirm('Удалить запись?')) {
            doDelete();
        }
    },
    
    async retry() {
        await loadAllData();
        this.render();
    }
};

// === TIMELINE ===
const Timeline = {
    data: [],
    
    async load() {
        try {
            this.data = await API.request('GET', '/api/timeline');
            this.render();
        } catch (e) {
            console.error('Timeline load error:', e);
        }
    },
    
    render() {
        const list = document.getElementById('timelineList');
        const empty = document.getElementById('timelineEmpty');
        
        if (this.data.length === 0) {
            list.innerHTML = '';
            empty.classList.add('show');
        } else {
            empty.classList.remove('show');
            list.innerHTML = this.data.map(item => this.renderItem(item)).join('');
        }
    },
    
    renderItem(item) {
        const icons = {
            created: '✨',
            updated: '✏️',
            deleted: '🗑️',
            completed: '✅',
            note_added: '📝'
        };
        
        const actionLabels = {
            created: 'Создано',
            updated: 'Обновлено',
            deleted: 'Удалено',
            completed: 'Выполнено',
            note_added: 'Заметка'
        };
        
        const entityLabels = {
            task: 'Задача',
            person: 'Человек',
            knowledge: 'Запись'
        };
        
        const entityColors = {
            task: 'var(--accent)',
            person: 'var(--warning)',
            knowledge: 'var(--success)'
        };
        
        const action = actionLabels[item.action_type] || item.action_type;
        const entity = entityLabels[item.entity_type] || item.entity_type;
        const icon = icons[item.action_type] || '📋';
        
        let clickAction = '';
        if (item.entity_type === 'task') {
            clickAction = `onclick="Nav.goto('tasksScreen');Tasks.openModal(${item.entity_id})"`;
        } else if (item.entity_type === 'person') {
            clickAction = `onclick="Nav.goto('peopleScreen');People.openCard(${item.entity_id})"`;
        } else if (item.entity_type === 'knowledge') {
            clickAction = `onclick="Nav.goto('knowledgeScreen');Knowledge.view(${item.entity_id})"`;
        }
        
        return `
            <div class="timeline-item ${item.action_type}">
                <div class="timeline-dot"></div>
                <div class="timeline-card" ${clickAction}>
                    <div class="timeline-header">
                        <span class="timeline-icon">${icon}</span>
                        <span class="timeline-action">${action}</span>
                        <span style="color:${entityColors[item.entity_type]};font-weight:600;font-size:12px;margin-left:auto">${entity}</span>
                    </div>
                    <div class="timeline-title">${Utils.escape(item.entity_title || 'Без названия')}</div>
                    ${item.details ? `<div class="timeline-details">${Utils.escape(item.details)}</div>` : ''}
                    <div class="timeline-time">${Utils.formatDateTime(item.created_at)}</div>
                </div>
            </div>
        `;
    },
    
    async retry() {
        await this.load();
    }
};

// === ИИ АССИСТЕНТ ===
const AI = {
    isLoading: false,
    
    async send() {
        const input = document.getElementById('chatInput');
        const text = input.value.trim();
        if (!text || this.isLoading) return;
        
        const messages = document.getElementById('chatMessages');
        const welcome = document.querySelector('.chat-welcome');
        if (welcome) welcome.style.display = 'none';
        
        // Сообщение пользователя
        messages.innerHTML += `<div class="chat-msg user">${Utils.escape(text)}</div>`;
        input.value = '';
        
        // Индикатор загрузки
        this.isLoading = true;
        const loadingId = Date.now();
        messages.innerHTML += `<div class="chat-msg ai loading" id="loading-${loadingId}">⏳ Думаю...</div>`;
        messages.scrollTop = messages.scrollHeight;
        
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 120000); // 2 минуты
            
            const response = await fetch(API_URL + '/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-User-Id': userId
                },
                body: JSON.stringify({ message: text }),
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            const data = await response.json();
            
            // Убираем загрузку и показываем ответ
            document.getElementById(`loading-${loadingId}`).remove();
            messages.innerHTML += `<div class="chat-msg ai">${Utils.escape(data.response)}</div>`;
            
        } catch (e) {
            document.getElementById(`loading-${loadingId}`).remove();
            messages.innerHTML += `<div class="chat-msg ai">❌ Ошибка соединения</div>`;
        }
        
        this.isLoading = false;
        messages.scrollTop = messages.scrollHeight;
        
        if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
    }
};

// === PULL-TO-REFRESH ===
function initPullToRefresh(containerId, refreshFn) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    let startY = 0;
    let currentY = 0;
    let isPulling = false;
    const threshold = 80;
    
    container.addEventListener('touchstart', (e) => {
        if (container.scrollTop === 0) {
            startY = e.touches[0].clientY;
            isPulling = true;
        }
    });
    
    container.addEventListener('touchmove', (e) => {
        if (!isPulling) return;
        
        currentY = e.touches[0].clientY;
        const pullDistance = currentY - startY;
        
        if (pullDistance > 0 && container.scrollTop === 0) {
            e.preventDefault();
            const pullRefresh = container.querySelector('.pull-refresh');
            if (pullRefresh) {
                const progress = Math.min(pullDistance / threshold, 1);
                pullRefresh.style.top = `${20 + progress * 30}px`;
                if (pullDistance > threshold) {
                    pullRefresh.classList.add('active');
                } else {
                    pullRefresh.classList.remove('active');
                }
            }
        }
    });
    
    container.addEventListener('touchend', () => {
        if (!isPulling) return;
        
        const pullRefresh = container.querySelector('.pull-refresh');
        if (pullRefresh && pullRefresh.classList.contains('active')) {
            refreshFn();
        }
        
        if (pullRefresh) {
            pullRefresh.style.top = '-50px';
            pullRefresh.classList.remove('active');
        }
        
        isPulling = false;
    });
}

// === ИНИЦИАЛИЗАЦИЯ ===
async function init() {
    Nav.init();
    Tasks.init();
    
    // Pull-to-refresh
    initPullToRefresh('todayContent', async () => {
        await loadAllData();
        Today.render();
        if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
    });
    
    initPullToRefresh('tasksContent', async () => {
        await loadAllData();
        Tasks.render();
        if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
    });
    
    initPullToRefresh('peopleContent', async () => {
        await loadAllData();
        People.render();
        if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
    });
    
    initPullToRefresh('knowledgeContent', async () => {
        await loadAllData();
        Knowledge.render();
        if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
    });
    
    initPullToRefresh('timelineContent', async () => {
        await Timeline.load();
        if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
    });
    
    await loadAllData();
    await Timeline.load();
    Today.render();
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
