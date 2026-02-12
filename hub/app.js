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
// tg.initData — сырая строка; на мобилке initDataUnsafe иногда пуст, API проверит initData

function getHeaders() {
    const h = { 'Content-Type': 'application/json', 'X-User-Id': userId };
    if (tg?.initData) h['X-Telegram-Init-Data'] = tg.initData;
    return h;
}

// === API ===
const API = {
    async request(method, endpoint, data = null) {
        const options = { method, headers: getHeaders() };
        if (data) options.body = JSON.stringify(data);
        
        try {
            const url = API_URL + endpoint;
            console.log(`API Request: ${method} ${url}`, data);
            
            const response = await fetch(url, options);
            
            if (!response.ok) {
                const clone = response.clone();
                let errorText = '';
                try {
                    const errorData = await clone.json();
                    errorText = errorData.detail || errorData.message || JSON.stringify(errorData);
                } catch {
                    try {
                        errorText = await clone.text();
                    } catch {
                        errorText = '';
                    }
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
    
    tomorrow() {
        const d = new Date();
        d.setDate(d.getDate() + 1);
        return d.toISOString().split('T')[0];
    },
    
    weekFromNow() {
        const d = new Date();
        d.setDate(d.getDate() + 7);
        return d.toISOString().split('T')[0];
    },
    
    monthFromNow() {
        const d = new Date();
        d.setDate(d.getDate() + 30);
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
    // Убирает префикс [Папка] при отображении — остаются только простые задачи
    displayTitle(title) {
        if (!title) return '';
        const m = title.match(/^\[[^\]]+\]\s*(.*)$/);
        return m ? m[1].trim() || title : title;
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
                removeFolderRemnants();
            } else if (screenId === 'tasksScreen') {
                Tasks.render();
                removeFolderRemnants(); // мобильный кеш может оставлять старый HTML
            } else if (screenId === 'financeScreen') {
                Finance.load();
            } else if (screenId === 'aiScreen') {
                AI.loadHistory();
            }
        }
    }
};

// Удаление остатков UI папок — на Главной, в Задачах, в модалках
function removeFolderRemnants() {
    const sel = '#statsScreen h3, #statsScreen h4, #statsScreen .folder-section, #statsScreen .filter, ' +
        '#tasksScreen h3, #tasksScreen h4, #tasksScreen .folder-section, #tasksFilters .filter, #taskModal .form-group';
    document.querySelectorAll(sel).forEach(el => {
        const t = (el.textContent || '').trim();
        const label = el.querySelector('label');
        if (t.startsWith('Без папки') || t.includes('Папка:') || (label && (label.textContent || '').includes('Папка'))) {
            el.remove();
        }
    });
}

// MutationObserver: удаляем «Без папки» и «Папка» при появлении в DOM
function watchFolderRemnants() {
    const obs = new MutationObserver(() => removeFolderRemnants());
    ['statsScreen', 'tasksScreen', 'taskModal'].forEach(id => {
        const el = document.getElementById(id);
        if (el) obs.observe(el, { childList: true, subtree: true });
    });
}

// === Данные ===
let tasksData = [];
let peopleData = [];
let projectsData = [];
let financeSummary = null;
let financeTransactions = [];
let financeGoals = [];
let financeLimits = [];

async function loadAllData(showLoading = true) {
    if (showLoading) {
        showLoadingState('tasks');
        showLoadingState('people');
        showLoadingState('projects');
    }
    
    try {
        [tasksData, peopleData, projectsData] = await Promise.all([
            API.request('GET', '/api/tasks'),
            API.request('GET', '/api/people'),
            API.request('GET', '/api/projects')
        ]);
        
        hideLoadingState('tasks');
        hideLoadingState('people');
        hideLoadingState('projects');
        hideErrorState('tasks');
        hideErrorState('people');
        hideErrorState('projects');
        
        // Обновляем все экраны сразу
        Today.render();
        removeFolderRemnants();
        Tasks.render();
        People.render();
        Projects.render();
    } catch (e) {
        console.error('Load error:', e);
        hideLoadingState('tasks');
        hideLoadingState('people');
        hideLoadingState('projects');
        showErrorState('tasks', e.message);
        showErrorState('people', e.message);
        showErrorState('projects', e.message);
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
        // Показываем задачи на сегодня + просроченные + без дедлайна
        const items = tasksData.filter(t => !t.done && (!t.deadline || t.deadline <= today));
        
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
        
        // Поиск в проектах
        projectsData.forEach(pr => {
            if (pr.title.toLowerCase().includes(query) || pr.description?.toLowerCase().includes(query)) {
                allResults.push({
                    type: 'project',
                    id: pr.id,
                    title: pr.title,
                    desc: pr.description?.substring(0, 100) || '',
                    icon: '📂',
                    action: () => { Nav.goto('projectsScreen'); Projects.openProject(pr.id); }
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
                        <span class="search-result-type">${r.type === 'task' ? 'Задача' : (r.type === 'person' ? 'Человек' : 'Проект')}</span>
                    </div>
                    <div class="search-result-title">${Utils.escape(r.type === 'task' ? Utils.displayTitle(r.title) : r.title)}</div>
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
            else if (type === 'project') Projects.openProject(id);
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
        const tomorrow = Utils.tomorrow();
        const week = Utils.weekFromNow();
        
        const month = Utils.monthFromNow();
        
        switch (this.filter) {
            case 'today': items = items.filter(t => !t.done && t.deadline === today); break;
            case 'tomorrow': items = items.filter(t => !t.done && t.deadline === tomorrow); break;
            case 'week': items = items.filter(t => !t.done && t.deadline && t.deadline <= week); break;
            case 'month': items = items.filter(t => !t.done && t.deadline && t.deadline <= month); break;
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
        Projects.updateProjectSelect();
        this.updateSortLabel();
        this.renderFilters(); // Перезаписываем фильтры — без папок
        removeFolderRemnants(); // мобильный WebView кеш — страховка
    },
    
    renderFilters() {
        const container = document.getElementById('tasksFilters');
        if (!container) return;
        container.innerHTML = `
            <button class="filter ${this.filter === 'all' ? 'active' : ''}" data-filter="all">Все</button>
            <button class="filter ${this.filter === 'today' ? 'active' : ''}" data-filter="today">Сегодня</button>
            <button class="filter ${this.filter === 'tomorrow' ? 'active' : ''}" data-filter="tomorrow">Завтра</button>
            <button class="filter ${this.filter === 'week' ? 'active' : ''}" data-filter="week">Неделя</button>
            <button class="filter ${this.filter === 'month' ? 'active' : ''}" data-filter="month">Месяц</button>
            <button class="filter ${this.filter === 'done' ? 'active' : ''}" data-filter="done">Готово</button>
        `;
        container.querySelectorAll('.filter').forEach(btn => {
            btn.addEventListener('click', () => {
                container.querySelectorAll('.filter').forEach(f => f.classList.remove('active'));
                btn.classList.add('active');
                this.filter = btn.dataset.filter;
                this.render();
            });
        });
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
        document.querySelectorAll('#tasksList .card-swipe-wrapper, #todayList .card-swipe-wrapper').forEach(wrapper => {
            const card = wrapper.querySelector('.card');
            if (!card) return;
            
            let startX = 0;
            let currentX = 0;
            let isSwiping = false;
            
            card.addEventListener('touchstart', (e) => {
                startX = e.touches[0].clientX;
                isSwiping = true;
                wrapper.classList.remove('show-left', 'show-right');
            });
            
            card.addEventListener('touchmove', (e) => {
                if (!isSwiping) return;
                currentX = e.touches[0].clientX - startX;
                
                card.style.transform = `translateX(${currentX}px)`;
                card.classList.add('swiping');
                
                // Показываем нужный индикатор
                if (currentX < -20) {
                    wrapper.classList.add('show-left');
                    wrapper.classList.remove('show-right');
                } else if (currentX > 20) {
                    wrapper.classList.add('show-right');
                    wrapper.classList.remove('show-left');
                } else {
                    wrapper.classList.remove('show-left', 'show-right');
                }
            });
            
            card.addEventListener('touchend', () => {
                card.classList.remove('swiping'); // Включаем плавную анимацию
                const taskId = parseInt(card.getAttribute('data-task-id'));
                
                // Свайп влево — удаление
                if (currentX < -80) {
                    card.style.transform = `translateX(-100%)`;
                    setTimeout(() => {
                        this.delete(taskId);
                    }, 250);
                }
                // Свайп вправо — выполнение
                else if (currentX > 80) {
                    card.style.transform = `translateX(100%)`;
                    setTimeout(() => {
                        this.toggle(taskId);
                    }, 250);
                }
                else {
                    card.style.transform = '';
                    setTimeout(() => {
                        wrapper.classList.remove('show-left', 'show-right');
                    }, 200);
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
        const hasReminder = task.reminder_enabled && task.reminder_time && task.reminder_time !== 'none';
        const isRepeated = task.recurrence_type && task.recurrence_type !== 'none';
        let reminderLabel = '';
        if (hasReminder) {
            if (task.reminder_time && task.reminder_time.startsWith('before_')) {
                const time = task.reminder_time.replace('before_', '');
                reminderLabel = `🔔 за день в ${time}`;
            } else {
                reminderLabel = `🔔 ${task.reminder_time}`;
            }
        }
        
        return `
            <div class="card-swipe-wrapper">
                <div class="swipe-indicator swipe-indicator-right">✓</div>
                <div class="swipe-indicator swipe-indicator-left">🗑</div>
                <div class="card ${task.done ? 'done' : ''}" data-task-id="${task.id}" onclick="Tasks.openModal(${task.id})">
                    <button class="card-delete" onclick="event.stopPropagation();Tasks.delete(${task.id})" title="Удалить">×</button>
                    <div class="card-header">
                        <div class="card-checkbox" onclick="event.stopPropagation();Tasks.toggle(${task.id})"></div>
                        <div class="card-body" style="flex:1">
                            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                                <span style="font-size:18px">${statusIcon}</span>
                                <div class="card-title" style="flex:1;margin:0">${Utils.escape(Utils.displayTitle(task.title))}</div>
                            </div>
                            ${task.description ? `<div class="card-desc">${Utils.escape(task.description)}</div>` : ''}
                            <div class="card-meta">
                                <span class="priority-badge ${task.priority || 'medium'}">
                                    ${priorityIcons[task.priority] || '🟡'} ${task.priority === 'high' ? 'Высокий' : (task.priority === 'low' ? 'Низкий' : 'Средний')}
                                </span>
                                ${task.deadline ? `<span class="${deadlineClass}">📅 ${Utils.formatDate(task.deadline)}</span>` : ''}
                                ${isRepeated ? `<span class="meta-pill">🔁 Повтор</span>` : ''}
                                ${hasReminder ? `<span class="meta-pill">${reminderLabel}</span>` : ''}
                            </div>
                            ${person ? `<div class="linked-person" style="margin-top:8px"><span class="avatar small">${Utils.initials(person.fio)}</span>${Utils.escape(person.fio)}</div>` : ''}
                        </div>
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
        document.getElementById('taskTitle').value = task ? Utils.displayTitle(task.title) : '';
        document.getElementById('taskDesc').value = task?.description || '';
        document.getElementById('taskDeadline').value = task?.deadline || Utils.today();
        document.getElementById('taskPriority').value = task?.priority || 'medium';
        document.getElementById('taskPerson').value = task?.person_id || '';
        const taskProjectSelect = document.getElementById('taskProject');
        if (taskProjectSelect) taskProjectSelect.value = task?.project_id || '';
        document.getElementById('taskDelete').style.display = task ? 'block' : 'none';
        
        const recurrence = task?.recurrence_type || 'none';
        document.getElementById('taskRecurrence').value = recurrence;
        
        const reminderSelect = document.getElementById('taskReminderSelect');
        if (task?.reminder_enabled && task.reminder_time) {
            reminderSelect.value = task.reminder_time;
        } else {
            reminderSelect.value = 'none';
        }
        
        // Скрываем поле папки, если осталось в старом HTML
        document.querySelectorAll('#taskForm .form-group').forEach(gr => {
            const label = gr.querySelector('label');
            if (label && (label.textContent || '').includes('Папка')) gr.style.display = 'none';
        });
        
        modal.classList.add('open');
    },
    
    closeModal() {
        document.getElementById('taskModal').classList.remove('open');
    },
    
    async save() {
        const id = document.getElementById('taskId').value;
        const reminderValue = document.getElementById('taskReminderSelect').value;
        const recurrenceValue = document.getElementById('taskRecurrence').value;
        const deadlineValue = document.getElementById('taskDeadline').value || null;
        let title = document.getElementById('taskTitle').value.trim();
        // Убираем остатки префикса [Папка] при сохранении
        const m = title.match(/^\[[^\]]+\]\s*(.*)$/);
        if (m) title = m[1].trim();
        const data = {
            title,
            description: document.getElementById('taskDesc').value.trim(),
            deadline: deadlineValue,
            priority: document.getElementById('taskPriority').value,
            person_id: parseInt(document.getElementById('taskPerson').value) || null,
            project_id: parseInt(document.getElementById('taskProject')?.value) || null,
            reminder_enabled: reminderValue !== 'none',
            reminder_time: reminderValue !== 'none' ? reminderValue : null,
            recurrence_type: recurrenceValue || 'none'
        };
        
        if (!data.title) return alert('Введите название');
        if (data.recurrence_type !== 'none' && !deadlineValue) {
            return (tg?.showAlert ? tg.showAlert('Для повторяющейся задачи нужно указать дедлайн.') : alert('Для повторяющейся задачи нужно указать дедлайн.'));
        }
        
        try {
            if (id) {
                await API.request('PATCH', `/api/tasks/${id}`, data);
            } else {
                await API.request('POST', '/api/tasks', data);
            }
            this.closeModal();
            await loadAllData(false);
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
            await loadAllData(false);
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
            await loadAllData(false);
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
        this.renderFilters(); // Фильтры без папок, обработчики в renderFilters
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
        const memberSelect = document.getElementById('projectMemberPerson');
        if (memberSelect) memberSelect.innerHTML = options;
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
                                        <div class="card-title" style="margin:0;font-size:15px">${Utils.escape(Utils.displayTitle(t.title))}</div>
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
        
        // Участие в проектах
        const relatedProjects = projectsData.filter(pr => pr.members?.some(m => m.person_id === person.id));
        if (relatedProjects.length) {
            html += `
                <div class="card-section">
                    <h4>Участвует в проектах (${relatedProjects.length})</h4>
                    ${relatedProjects.map(pr => {
                        const member = pr.members.find(m => m.person_id === person.id);
                        const statusLabels = {active: '🟢', paused: '⏸️', done: '✅'};
                        return `
                        <div class="card linked-project" onclick="Nav.goto('projectsScreen');Projects.openProject(${pr.id})" style="margin-bottom:8px;cursor:pointer">
                            <div style="display:flex;align-items:center;gap:8px">
                                <span style="font-size:16px">${statusLabels[pr.status] || '📂'}</span>
                                <div style="flex:1">
                                    <div class="card-title" style="margin:0;font-size:15px">${Utils.escape(pr.title)}</div>
                                    ${member?.role ? `<div style="font-size:12px;color:var(--text-secondary);margin-top:4px">${Utils.escape(member.role)}</div>` : ''}
                                </div>
                                <span style="color:var(--accent);font-size:18px">→</span>
                            </div>
                        </div>
                    `}).join('')}
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
            await loadAllData(false);
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
            await loadAllData(false);
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
            await loadAllData(false);
            const person = peopleData.find(p => p.id === this.currentId);
            if (person) this.renderCard(person);
        } catch (e) {}
    },
    
    async deleteNote(noteId) {
        const doDelete = async () => {
            await API.request('DELETE', `/api/people/${this.currentId}/notes/${noteId}`);
            await loadAllData(false);
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

// === ПРОЕКТЫ ===
const Projects = {
    currentId: null,
    filter: 'all',
    
    async render() {
        const list = document.getElementById('projectsList');
        const empty = document.getElementById('projectsEmpty');
        
        hideLoadingState('projects');
        hideErrorState('projects');
        
        let items = [...projectsData];
        
        if (this.filter !== 'all') {
            items = items.filter(pr => pr.status === this.filter);
        }
        
        if (items.length === 0) {
            list.innerHTML = '';
            empty.classList.add('show');
        } else {
            empty.classList.remove('show');
            list.innerHTML = items.map(pr => this.renderItem(pr)).join('');
        }
        
        this.renderFilters();
        this.updateProjectSelect();
    },
    
    renderItem(project) {
        const statusLabels = {active: '🟢 Активный', paused: '⏸️ На паузе', done: '✅ Завершён'};
        const statusColors = {active: 'var(--success)', paused: 'var(--warning)', done: 'var(--text-secondary)'};
        
        const totalTasks = project.tasks_count || 0;
        const doneTasks = project.tasks_done || 0;
        const pct = totalTasks > 0 ? Math.round(doneTasks / totalTasks * 100) : 0;
        
        let finMeta = '';
        if (project.budget) finMeta += `💰 ${Number(project.budget).toFixed(0)}`;
        if (project.revenue_goal) finMeta += `${finMeta ? ' · ' : ''}🎯 ${Number(project.revenue_goal).toFixed(0)}`;
        
        return `
            <div class="card" onclick="Projects.openProject(${project.id})" style="position:relative">
                <button class="card-delete" onclick="event.stopPropagation();Projects.delete(${project.id})" title="Удалить">×</button>
                <div class="card-title">${Utils.escape(project.title)}</div>
                ${project.description ? `<div class="card-desc">${Utils.escape(project.description)}</div>` : ''}
                <div class="card-meta">
                    <span style="color:${statusColors[project.status] || 'var(--text-secondary)'}">${statusLabels[project.status] || project.status}</span>
                    ${project.deadline ? `<span>📅 ${Utils.formatDate(project.deadline)}</span>` : ''}
                    ${project.members_count ? `<span>👥 ${project.members_count}</span>` : ''}
                </div>
                ${totalTasks > 0 ? `
                <div class="project-progress" style="margin-top:8px">
                    <div class="goal-progress">
                        <div class="bar"><div class="fill" style="width:${pct}%"></div></div>
                        <div class="text">${doneTasks}/${totalTasks} задач (${pct}%)</div>
                    </div>
                </div>` : ''}
                ${finMeta ? `<div style="margin-top:6px;font-size:12px;color:var(--text-secondary)">${finMeta}</div>` : ''}
            </div>
        `;
    },
    
    renderFilters() {
        const container = document.getElementById('projectsFilters');
        if (!container) return;
        container.innerHTML = `
            <button class="filter ${this.filter === 'all' ? 'active' : ''}" data-filter="all">Все</button>
            <button class="filter ${this.filter === 'active' ? 'active' : ''}" data-filter="active">Активные</button>
            <button class="filter ${this.filter === 'paused' ? 'active' : ''}" data-filter="paused">На паузе</button>
            <button class="filter ${this.filter === 'done' ? 'active' : ''}" data-filter="done">Завершённые</button>
        `;
        container.querySelectorAll('.filter').forEach(btn => {
            btn.addEventListener('click', () => {
                this.filter = btn.dataset.filter;
                this.render();
            });
        });
    },
    
    updateProjectSelect() {
        const select = document.getElementById('taskProject');
        if (!select) return;
        select.innerHTML = '<option value="">— Не выбрано —</option>' +
            projectsData.filter(p => p.status === 'active').map(p => `<option value="${p.id}">${Utils.escape(p.title)}</option>`).join('');
    },
    
    async openProject(id) {
        const project = projectsData.find(pr => pr.id === id);
        if (!project) return;
        
        this.currentId = id;
        document.getElementById('projectTitle').textContent = project.title;
        
        // Load full project with summary
        try {
            const summary = await API.request('GET', `/api/projects/${id}/summary`);
            this.renderProject(project, summary);
        } catch (e) {
            this.renderProject(project, null);
        }
        
        Nav.goto('projectScreen');
    },
    
    closeProject() {
        Nav.goto('projectsScreen');
        this.currentId = null;
    },
    
    renderProject(project, summary) {
        const statusLabels = {active: '🟢 Активный', paused: '⏸️ На паузе', done: '✅ Завершён'};
        const totalTasks = summary?.tasks_total || 0;
        const doneTasks = summary?.tasks_done || 0;
        const pct = totalTasks > 0 ? Math.round(doneTasks / totalTasks * 100) : 0;
        
        const tasks = summary?.tasks || [];
        const members = project.members || [];
        const notes = summary?.notes || [];
        
        let html = '';
        
        // Шапка
        html += `
            <div class="card-section">
                <div class="card-field"><label>Статус</label><p>${statusLabels[project.status] || project.status}</p></div>
                ${project.deadline ? `<div class="card-field"><label>Дедлайн</label><p>📅 ${Utils.formatDate(project.deadline)}</p></div>` : ''}
                ${project.description ? `<div class="card-field"><label>Описание</label><p>${Utils.escape(project.description)}</p></div>` : ''}
            </div>
        `;
        
        // Прогресс
        if (totalTasks > 0) {
            html += `
                <div class="card-section">
                    <h4>Прогресс</h4>
                    <div class="goal-progress">
                        <div class="bar"><div class="fill" style="width:${pct}%"></div></div>
                        <div class="text">${doneTasks}/${totalTasks} задач выполнено (${pct}%)</div>
                    </div>
                </div>
            `;
        }
        
        // Финансы
        if (project.budget || project.revenue_goal) {
            html += `<div class="card-section"><h4>Финансы</h4>`;
            if (project.budget) html += `<div class="card-field"><label>Бюджет</label><p>💰 ${Number(project.budget).toFixed(0)}</p></div>`;
            if (project.revenue_goal) html += `<div class="card-field"><label>Цель по доходу</label><p>🎯 ${Number(project.revenue_goal).toFixed(0)}</p></div>`;
            html += `</div>`;
        }
        
        // Задачи
        html += `
            <div class="card-section">
                <div class="notes-header">
                    <h4>Задачи (${totalTasks})</h4>
                    <button class="btn-add-note" onclick="Projects.addTask()">+ Добавить</button>
                </div>
                ${tasks.length ? tasks.map(t => {
                    const today = Utils.today();
                    const deadlineClass = t.deadline ? (t.deadline < today ? 'overdue' : (t.deadline === today ? 'today' : '')) : '';
                    return `
                        <div class="card ${t.done ? 'done' : ''}" onclick="Tasks.openModal(${t.id})" style="margin-bottom:8px;cursor:pointer">
                            <div style="display:flex;align-items:center;gap:8px">
                                <span style="font-size:16px">${t.done ? '✅' : '📋'}</span>
                                <div style="flex:1">
                                    <div class="card-title" style="margin:0;font-size:15px">${Utils.escape(Utils.displayTitle(t.title))}</div>
                                    ${t.deadline ? `<div style="font-size:12px;color:var(--text-secondary);margin-top:4px" class="${deadlineClass}">📅 ${Utils.formatDate(t.deadline)}</div>` : ''}
                                </div>
                            </div>
                        </div>
                    `;
                }).join('') : '<p class="empty">Нет задач</p>'}
            </div>
        `;
        
        // Команда
        html += `
            <div class="card-section">
                <div class="notes-header">
                    <h4>Команда (${members.length})</h4>
                    <button class="btn-add-note" onclick="Projects.openMemberModal()">+ Добавить</button>
                </div>
                ${members.length ? members.map(m => {
                    const person = peopleData.find(p => p.id === m.person_id);
                    if (!person) return '';
                    return `
                        <div class="person-item" style="position:relative;padding:8px 12px" onclick="People.openCard(${person.id})">
                            <button class="card-delete" onclick="event.stopPropagation();Projects.removeMember(${m.id})" title="Убрать" style="position:absolute;top:8px;right:8px">×</button>
                            <div class="avatar small">${Utils.initials(person.fio)}</div>
                            <div class="person-info">
                                <h3 style="font-size:14px;margin:0">${Utils.escape(person.fio)}</h3>
                                ${m.role ? `<p style="font-size:12px;margin:2px 0 0">${Utils.escape(m.role)}</p>` : ''}
                            </div>
                        </div>
                    `;
                }).join('') : '<p class="empty">Нет участников</p>'}
            </div>
        `;
        
        // Лог заметок
        html += `
            <div class="card-section">
                <div class="notes-header">
                    <h4>Лог</h4>
                    <button class="btn-add-note" onclick="Projects.openNoteModal()">+ Добавить</button>
                </div>
                ${notes.length ? notes.map(n => `
                    <div class="note-item">
                        <div class="note-date">${Utils.formatDateTime(n.created_at)}</div>
                        <div class="note-text">${Utils.escape(n.text)}</div>
                        <button class="note-delete" onclick="Projects.deleteNote(${n.id})">Удалить</button>
                    </div>
                `).join('') : '<p class="empty">Нет заметок</p>'}
            </div>
        `;
        
        document.getElementById('projectCard').innerHTML = html;
    },
    
    addTask() {
        Tasks.openModal();
        // Pre-select this project
        setTimeout(() => {
            const select = document.getElementById('taskProject');
            if (select && this.currentId) select.value = this.currentId;
        }, 100);
    },
    
    openModal(id = null) {
        const project = id ? projectsData.find(pr => pr.id === id) : null;
        
        document.getElementById('projectModalTitle').textContent = project ? 'Редактировать' : 'Новый проект';
        document.getElementById('projectId').value = project ? project.id : '';
        document.getElementById('projectName').value = project?.title || '';
        document.getElementById('projectDesc').value = project?.description || '';
        document.getElementById('projectStatus').value = project?.status || 'active';
        document.getElementById('projectDeadline').value = project?.deadline || '';
        document.getElementById('projectBudget').value = project?.budget || '';
        document.getElementById('projectRevenueGoal').value = project?.revenue_goal || '';
        
        document.getElementById('projectDelete').style.display = project ? 'block' : 'none';
        document.getElementById('projectModal').classList.add('open');
    },
    
    closeModal() {
        document.getElementById('projectModal').classList.remove('open');
    },
    
    edit() {
        this.openModal(this.currentId);
    },
    
    async save() {
        const id = document.getElementById('projectId').value;
        const data = {
            title: document.getElementById('projectName').value.trim(),
            description: document.getElementById('projectDesc').value.trim(),
            status: document.getElementById('projectStatus').value,
            deadline: document.getElementById('projectDeadline').value || null,
            budget: parseFloat(document.getElementById('projectBudget').value) || null,
            revenue_goal: parseFloat(document.getElementById('projectRevenueGoal').value) || null
        };
        
        if (!data.title) return alert('Введите название');
        
        try {
            if (id) {
                await API.request('PATCH', `/api/projects/${id}`, data);
            } else {
                const result = await API.request('POST', '/api/projects', data);
                this.currentId = result.id;
            }
            this.closeModal();
            await loadAllData(false);
            this.render();
            
            if (this.currentId) {
                const pr = projectsData.find(p => p.id === this.currentId);
                if (pr) {
                    document.getElementById('projectTitle').textContent = pr.title;
                    try {
                        const summary = await API.request('GET', `/api/projects/${this.currentId}/summary`);
                        this.renderProject(pr, summary);
                    } catch (e) { this.renderProject(pr, null); }
                }
            }
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        } catch (e) {
            console.error('Save error:', e);
            const errorMsg = e.message || 'Ошибка сохранения';
            if (tg?.showAlert) tg.showAlert(`Ошибка: ${errorMsg}`);
            else alert(`Ошибка сохранения: ${errorMsg}`);
        }
    },
    
    async delete(id = null) {
        const projectId = id || document.getElementById('projectId').value;
        if (!projectId) return;
        
        const doDelete = async () => {
            await API.request('DELETE', `/api/projects/${projectId}`);
            if (!id) {
                this.closeModal();
                this.closeProject();
            }
            await loadAllData(false);
            this.render();
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        };
        
        if (tg?.showConfirm) tg.showConfirm('Удалить проект?', ok => { if (ok) doDelete(); });
        else if (confirm('Удалить проект?')) doDelete();
    },
    
    // Members
    openMemberModal() {
        People.updateSelects();
        document.getElementById('projectMemberPerson').value = '';
        document.getElementById('projectMemberRole').value = '';
        document.getElementById('projectMemberModal').classList.add('open');
    },
    
    closeMemberModal() {
        document.getElementById('projectMemberModal').classList.remove('open');
    },
    
    async saveMember() {
        const personId = parseInt(document.getElementById('projectMemberPerson').value);
        const role = document.getElementById('projectMemberRole').value.trim();
        if (!personId) return alert('Выберите человека');
        
        try {
            await API.request('POST', `/api/projects/${this.currentId}/members`, { person_id: personId, role });
            this.closeMemberModal();
            await loadAllData(false);
            await this.openProject(this.currentId);
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        } catch (e) {
            const msg = e.message || 'Ошибка';
            if (tg?.showAlert) tg.showAlert(msg); else alert(msg);
        }
    },
    
    async removeMember(memberId) {
        const doDelete = async () => {
            await API.request('DELETE', `/api/projects/${this.currentId}/members/${memberId}`);
            await loadAllData(false);
            await this.openProject(this.currentId);
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        };
        if (tg?.showConfirm) tg.showConfirm('Убрать участника?', ok => { if (ok) doDelete(); });
        else if (confirm('Убрать участника?')) doDelete();
    },
    
    // Notes
    openNoteModal() {
        document.getElementById('projectNoteText').value = '';
        document.getElementById('projectNoteModal').classList.add('open');
    },
    
    closeNoteModal() {
        document.getElementById('projectNoteModal').classList.remove('open');
    },
    
    async saveNote() {
        const text = document.getElementById('projectNoteText').value.trim();
        if (!text) return;
        
        try {
            await API.request('POST', `/api/projects/${this.currentId}/notes`, { text });
            this.closeNoteModal();
            await this.openProject(this.currentId);
        } catch (e) {}
    },
    
    async deleteNote(noteId) {
        const doDelete = async () => {
            await API.request('DELETE', `/api/projects/${this.currentId}/notes/${noteId}`);
            await this.openProject(this.currentId);
        };
        if (tg?.showConfirm) tg.showConfirm('Удалить заметку?', ok => { if (ok) doDelete(); });
        else if (confirm('Удалить?')) doDelete();
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
            project: 'Проект'
        };
        
        const entityColors = {
            task: 'var(--accent)',
            person: 'var(--warning)',
            project: 'var(--success)'
        };
        
        const action = actionLabels[item.action_type] || item.action_type;
        const entity = entityLabels[item.entity_type] || item.entity_type;
        const icon = icons[item.action_type] || '📋';
        
        let clickAction = '';
        if (item.entity_type === 'task') {
            clickAction = `onclick="Nav.goto('tasksScreen');Tasks.openModal(${item.entity_id})"`;
        } else if (item.entity_type === 'person') {
            clickAction = `onclick="Nav.goto('peopleScreen');People.openCard(${item.entity_id})"`;
        } else if (item.entity_type === 'project') {
            clickAction = `onclick="Nav.goto('projectsScreen');Projects.openProject(${item.entity_id})"`;
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
    isHistoryLoaded: false,
    
    async loadHistory() {
        if (this.isHistoryLoaded) return;
        const messages = document.getElementById('chatMessages');
        const welcome = document.querySelector('.chat-welcome');
        try {
            const data = await API.request('GET', '/api/chat/history');
            const history = data.history || [];
            if (!history.length) return;
            if (welcome) welcome.style.display = 'none';
            messages.innerHTML = '';
            history.forEach(h => {
                if (h.role === 'user') {
                    messages.innerHTML += `<div class="chat-msg user">${Utils.escape(h.content)}</div>`;
                } else {
                    messages.innerHTML += `<div class="chat-msg ai">${Utils.escape(h.content)}</div>`;
                }
            });
            messages.scrollTop = messages.scrollHeight;
            this.isHistoryLoaded = true;
        } catch (e) {
            console.error('AI history load error:', e);
        }
    },

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
                headers: getHeaders(),
                body: JSON.stringify({ message: text }),
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            const data = await response.json();
            
            // Убираем загрузку и показываем ответ
            document.getElementById(`loading-${loadingId}`).remove();
            
            const isAction = !!data.action_executed;
            const meta = isAction
                ? '<div class="chat-msg-meta">⚙ Выполнено действие в системе</div>'
                : '';
            
            messages.innerHTML += `
                <div class="chat-msg ai${isAction ? ' action' : ''}">
                    ${Utils.escape(data.response)}
                    ${meta}
                </div>
            `;
            
            // Если ИИ выполнил действие — обновляем данные
            if (isAction) {
                await loadAllData(true); // Принудительное обновление
                if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
            }
            
        } catch (e) {
            document.getElementById(`loading-${loadingId}`).remove();
            messages.innerHTML += `<div class="chat-msg ai">❌ Ошибка соединения</div>`;
        }
        
        this.isLoading = false;
        messages.scrollTop = messages.scrollHeight;
        
        if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
    },
    
    async clearHistory() {
        if (!confirm('Очистить историю диалога?')) return;
        
        try {
            await fetch(API_URL + '/api/chat/history', {
                method: 'DELETE',
                headers: getHeaders()
            });
            
            // Очищаем UI
            const messages = document.getElementById('chatMessages');
            messages.innerHTML = `
                <div class="chat-welcome">
                    <div class="chat-welcome-icon">🤖</div>
                    <p>Привет! Я твой ИИ-ассистент.</p>
                    <p>Спроси меня о задачах, людях или проектах.</p>
                </div>
            `;
            
            if (tg?.showAlert) tg.showAlert('История очищена');
        } catch (e) {
            console.error('Ошибка очистки истории:', e);
        }
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
    
    initPullToRefresh('projectsContent', async () => {
        await loadAllData();
        Projects.render();
        if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
    });
    
    await loadAllData();
    Today.render();
    Tasks.render();
    People.render();
    Projects.render();
    removeFolderRemnants();
    watchFolderRemnants(); // Удаляем папки при любом добавлении в DOM
    await Finance.load();
    
    // Закрытие модалов
    document.querySelectorAll('.modal').forEach(m => {
        m.addEventListener('click', e => {
            if (e.target === m) m.classList.remove('open');
        });
    });

    // Автопереключение при возврате в приложение
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible') return;
        removeFolderRemnants(); // мобильный — убираем папки при возврате
        const financeScreen = document.getElementById('financeScreen');
        if (!financeScreen || !financeScreen.classList.contains('active')) return;
        const now = new Date();
        const currentMonthStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
        if (Finance.currentMonth && Finance.currentMonth !== currentMonthStr) {
            Finance.load();
        }
    });
}

init();

// === ФИНАНСЫ ===
const Finance = {
    currentMonth: null,
    filterType: 'balance',   // 'income' | 'expense' | 'balance' (balance = все операции)
    filterCategory: null,

    async load(month = null) {
        const empty = document.getElementById('financeEmpty');
        const main = document.getElementById('financeMain');
        try {
            const now = new Date();
            if (!month) {
                month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
            }
            this.currentMonth = month;
            const query = `?month=${month}`;
            const summary = await API.request('GET', `/api/finance/summary${query}`);
            const txs = await API.request('GET', `/api/finance/transactions${query}`);
            financeSummary = summary;
            financeTransactions = Array.isArray(txs) ? txs : [];
            financeGoals = Array.isArray(summary?.goals) ? summary.goals : [];
            if (empty) empty.classList.remove('show');
            if (main) main.style.display = 'block';
            this.render();
        } catch (e) {
            console.error('Finance load error:', e);
            financeSummary = null;
            financeTransactions = [];
            financeGoals = [];
            if (empty) {
                empty.textContent = 'Ошибка загрузки финансовых данных';
                empty.classList.add('show');
            }
            if (main) main.style.display = 'none';
            this.render();
        }
    },

    render() {
        const main = document.getElementById('financeMain');
        const empty = document.getElementById('financeEmpty');
        if (!main) return;

        if (!financeSummary || !Number.isFinite(financeSummary.income) && !Number.isFinite(financeSummary.expense)) {
            main.style.display = 'none';
            if (empty) empty.classList.add('show');
            return;
        }

        const income = Number(financeSummary.income) || 0;
        const expense = Number(financeSummary.expense) || 0;
        const balance = Number(financeSummary.balance) ?? (income - expense);
        const goals = Array.isArray(financeGoals) ? financeGoals : [];
        const txs = Array.isArray(financeTransactions) ? financeTransactions : [];
        const monthLabel = this.formatMonthLabel(this.currentMonth);

        let filtered = txs;
        if (this.filterType === 'income') filtered = txs.filter(t => (t.type || '').toLowerCase() === 'income');
        else if (this.filterType === 'expense') filtered = txs.filter(t => (t.type || '').toLowerCase() === 'expense');
        // balance = показываем все
        if (this.filterCategory) {
            filtered = filtered.filter(t => (t.category || '').trim() === this.filterCategory);
        }

        const categoriesForType = [];
        if (this.filterType === 'income') {
            const set = new Set();
            txs.filter(t => (t.type || '').toLowerCase() === 'income').forEach(t => { if (t.category) set.add(t.category.trim()); });
            categoriesForType.push(...set);
        } else if (this.filterType === 'expense') {
            const set = new Set();
            txs.filter(t => (t.type || '').toLowerCase() === 'expense').forEach(t => { if (t.category) set.add(t.category.trim()); });
            categoriesForType.push(...set);
        }
        const totalFiltered = filtered.reduce((sum, t) => {
            const amt = Number(t.amount) || 0;
            const type = (t.type || '').toLowerCase();
            if (type === 'income') return sum + amt;
            if (type === 'expense') return sum - amt;
            return sum;
        }, 0);

        const goalsTotalSum = goals.reduce((s, g) => s + (Number(g.current_amount) || 0), 0);

        let summaryText = '';
        if (!income && !expense) {
            summaryText = `За ${monthLabel.toLowerCase()} пока нет операций.`;
        } else {
            if (balance >= 0) {
                summaryText = `За ${monthLabel.toLowerCase()} вы в плюсе на ${balance.toFixed(0)}.`;
            } else {
                summaryText = `За ${monthLabel.toLowerCase()} вы потратили больше доходов на ${Math.abs(balance).toFixed(0)}.`;
            }
        }

        const cardClass = (type) => {
            const active = this.filterType === type;
            const base = type === 'income' ? 'finance-card income' : type === 'expense' ? 'finance-card expense' : 'finance-card balance';
            return active ? base + ' active' : base + ' clickable';
        };

        main.innerHTML = `
            <div class="finance-block">
                <div class="finance-month-bar">
                    <button class="month-btn" onclick="Finance.shiftMonth(-1)">◀</button>
                    <span class="finance-month-label">${monthLabel}</span>
                    <button class="month-btn" onclick="Finance.shiftMonth(1)">▶</button>
                </div>
                <div class="finance-actions">
                    <button class="btn-primary" onclick="Finance.openTxModal()">💸 Добавить операцию</button>
                    <button class="btn-secondary" onclick="Finance.openLimitsModal()">📊 Лимиты</button>
                </div>
                <div class="finance-summary">
                    <div class="${cardClass('income')}" onclick="Finance.setFilterType('income')" role="button">
                        <div class="label">Доход</div>
                        <div class="value">+${income.toFixed(0)}</div>
                    </div>
                    <div class="${cardClass('expense')}" onclick="Finance.setFilterType('expense')" role="button">
                        <div class="label">Расход</div>
                        <div class="value">-${expense.toFixed(0)}</div>
                    </div>
                    <div class="${cardClass('balance')}" onclick="Finance.setFilterType('balance')" role="button">
                        <div class="label">Баланс</div>
                        <div class="value">${balance.toFixed(0)}</div>
                    </div>
                </div>
                <div class="finance-summary-text">${summaryText}</div>

                ${(this.filterType === 'income' || this.filterType === 'expense') && categoriesForType.length > 0 ? `
                <div class="finance-category-pills">
                    <button type="button" class="filter ${!this.filterCategory ? 'active' : ''}" onclick="Finance.setFilterCategory(null)">Все</button>
                    ${categoriesForType.sort().map(c => `
                        <button type="button" class="filter ${this.filterCategory === c ? 'active' : ''}" onclick="Finance.setFilterCategory('${Utils.escape(c).replace(/'/g, "\\'")}')">${Utils.escape(c)}</button>
                    `).join('')}
                </div>
                ` : ''}

                <h3>Операции</h3>
                ${filtered.length === 0 ? '<div class="empty small show">Нет операций</div>' : `
                <ul class="finance-transactions-list">
                    ${filtered.map(t => this.renderTxItem(t)).join('')}
                </ul>
                ${(this.filterCategory || this.filterType !== 'balance') && filtered.length > 0 ? `
                <div class="finance-filtered-total">Итого: <strong>${totalFiltered >= 0 ? '+' : ''}${totalFiltered.toFixed(0)}</strong></div>
                ` : ''}
                `}
            </div>

            <div class="finance-block">
                <h3 class="finance-goals-heading">Цели <span class="finance-goals-total">${goalsTotalSum.toFixed(0)}</span></h3>
                <div class="finance-actions">
                    <button class="btn-secondary" onclick="Finance.openGoalModal()">🎯 Добавить цель</button>
                </div>
                ${goals.length === 0 ? '<div class="empty small show">Цели ещё не созданы</div>' : `
                <ul class="finance-goals">
                    ${goals.map(g => {
                        const target = Number(g.target_amount) || 0;
                        const current = Number(g.current_amount) || 0;
                        const pct = target > 0 ? Math.min(100, Math.round(current / target * 100)) : 0;
                        return `
                            <li onclick="Finance.openGoalModal(${g.id})" class="goal-item-clickable">
                                <div class="goal-title">${Utils.escape(g.title)}</div>
                                <div class="goal-progress">
                                    <div class="bar"><div class="fill" style="width:${pct}%"></div></div>
                                    <div class="text">${current.toFixed(0)} / ${target.toFixed(0)} (${pct}%)</div>
                                </div>
                            </li>
                        `;
                    }).join('')}
                </ul>`}
            </div>
        `;
    },

    setFilterType(type) {
        this.filterType = type;
        this.filterCategory = null;
        this.render();
    },

    setFilterCategory(cat) {
        this.filterCategory = cat;
        this.render();
    },

    renderTxItem(t) {
        const type = (t.type || '').toLowerCase();
        const isIncome = type === 'income';
        const isSavings = type === 'savings';
        const amount = Number(t.amount) || 0;
        const dateStr = t.date ? Utils.formatDate(t.date) : '';
        const amountClass = isSavings ? 'savings' : (isIncome ? 'income' : 'expense');
        const amountSign = isSavings || isIncome ? '+' : '-';
        return `
            <li class="finance-tx-item" onclick="Finance.openTxModal(${t.id})" data-tx-id="${t.id}">
                <button type="button" class="finance-tx-delete" onclick="event.stopPropagation();Finance.deleteTransaction(${t.id})" title="Удалить">×</button>
                <div class="finance-tx-main">
                    <span class="finance-tx-cat">${Utils.escape(t.category || 'Прочее')}</span>
                    <span class="finance-tx-amount ${amountClass}">${amountSign}${amount.toFixed(0)}</span>
                </div>
                <div class="finance-tx-meta">${dateStr}${t.comment ? ' · ' + Utils.escape(t.comment) : ''}</div>
            </li>
        `;
    },

    formatMonthLabel(monthStr) {
        if (!monthStr) return '';
        const [y, m] = monthStr.split('-').map(Number);
        const d = new Date(y, m - 1, 1);
        return d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
    },

    shiftMonth(delta) {
        if (!this.currentMonth) {
            const now = new Date();
            this.currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
        }
        let [y, m] = this.currentMonth.split('-').map(Number);
        m += delta;
        if (m < 1) {
            m = 12;
            y -= 1;
        } else if (m > 12) {
            m = 1;
            y += 1;
        }
        const newMonth = `${y}-${String(m).padStart(2, '0')}`;
        this.load(newMonth);
    },
    
    openTxModal(id = null) {
        const modal = document.getElementById('financeTxModal');
        const titleEl = document.getElementById('financeTxModalTitle');
        const txIdEl = document.getElementById('txId');
        if (!modal || !txIdEl) return;

        const tx = id ? (financeTransactions || []).find(t => t.id === id) : null;
        if (titleEl) titleEl.textContent = tx ? 'Редактировать операцию' : 'Новая операция';
        txIdEl.value = tx ? tx.id : '';

        document.getElementById('txType').value = tx ? (tx.type || 'expense') : 'expense';
        document.getElementById('txDate').value = tx?.date ? tx.date.split('T')[0] : Utils.today();
        document.getElementById('txAmount').value = tx ? (Number(tx.amount) || '') : '';
        document.getElementById('txCategory').value = tx?.category || '';
        document.getElementById('txComment').value = tx?.comment || '';

        this.onTypeChange();
        const catInput = document.getElementById('txCategory');
        const suggestions = document.getElementById('txCategorySuggestions');
        if (catInput && suggestions) {
            suggestions.style.display = 'none';
            if (!catInput._hasFocusListener) {
                catInput.addEventListener('focus', () => { suggestions.style.display = 'flex'; });
                catInput.addEventListener('blur', () => { setTimeout(() => { suggestions.style.display = 'none'; }, 150); });
                catInput._hasFocusListener = true;
            }
        }
        const typeSelect = document.getElementById('txType');
        if (typeSelect && !typeSelect._hasListener) {
            typeSelect.addEventListener('change', () => this.onTypeChange());
            typeSelect._hasListener = true;
        }
        modal.classList.add('open');
    },
    
    closeTxModal() {
        const modal = document.getElementById('financeTxModal');
        if (modal) modal.classList.remove('open');
    },
    
    async saveTransaction() {
        const id = document.getElementById('txId').value.trim();
        const type = document.getElementById('txType').value;
        const date = document.getElementById('txDate').value || Utils.today();
        const amountStr = document.getElementById('txAmount').value;
        const category = document.getElementById('txCategory').value.trim() || 'Прочее';
        const comment = document.getElementById('txComment').value.trim();
        const amount = parseFloat(amountStr);
        if (!amount || amount <= 0) {
            return (tg?.showAlert ? tg.showAlert('Введите сумму операции') : alert('Введите сумму операции'));
        }
        const payload = { type, date, amount, category, comment };
        try {
            if (id) {
                await API.request('PATCH', `/api/finance/transactions/${id}`, payload);
            } else {
                await API.request('POST', '/api/finance/transactions', payload);
            }
            this.closeTxModal();
            await this.load();
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        } catch (e) {
            console.error('Finance tx save error:', e);
            const msg = e.message || 'Ошибка сохранения операции';
            if (tg?.showAlert) tg.showAlert(msg); else alert(msg);
        }
    },

    async deleteTransaction(id) {
        const doDelete = async () => {
            try {
                await API.request('DELETE', `/api/finance/transactions/${id}`);
                await this.load();
                if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
            } catch (e) {
                console.error('Finance tx delete error:', e);
                if (tg?.showAlert) tg.showAlert(e.message || 'Ошибка удаления'); else alert(e.message);
            }
        };
        if (tg?.showConfirm) tg.showConfirm('Удалить операцию?', ok => { if (ok) doDelete(); });
        else if (confirm('Удалить операцию?')) doDelete();
    },

    setCategory(name) {
        const input = document.getElementById('txCategory');
        if (!input) return;
        input.value = name;
        input.focus();
    },

    onTypeChange() {
        const type = document.getElementById('txType')?.value;
        const suggestions = document.getElementById('txCategorySuggestions');
        if (suggestions) {
            const exp = suggestions.querySelector('.tags-expense');
            const inc = suggestions.querySelector('.tags-income');
            if (exp && inc) {
                if (type === 'income') {
                    exp.style.display = 'none';
                    inc.style.display = 'flex';
                } else {
                    exp.style.display = 'flex';
                    inc.style.display = 'none';
                }
            }
        }
    },
    
    openGoalModal(id = null) {
        const modal = document.getElementById('financeGoalModal');
        const titleEl = document.getElementById('financeGoalModalTitle');
        const goalIdEl = document.getElementById('goalId');
        const deleteBtn = document.getElementById('goalDeleteBtn');
        if (!modal || !goalIdEl) return;

        const goal = id ? (financeGoals || []).find(g => g.id === id) : null;
        if (titleEl) titleEl.textContent = goal ? 'Редактировать цель' : 'Новая цель';
        goalIdEl.value = goal ? goal.id : '';
        if (deleteBtn) deleteBtn.style.display = goal ? 'block' : 'none';

        document.getElementById('goalTitle').value = goal?.title || '';
        document.getElementById('goalTarget').value = goal ? (Number(goal.target_amount) || '') : '';
        document.getElementById('goalCurrent').value = goal ? (Number(goal.current_amount) || '') : '';
        document.getElementById('goalDate').value = goal?.target_date ? goal.target_date.split('T')[0] : '';
        document.getElementById('goalPriority').value = goal?.priority != null ? String(goal.priority) : '1';
        const topUpEl = document.getElementById('goalTopUpAmount');
        if (topUpEl) topUpEl.value = '';
        modal.classList.add('open');
    },

    async addToGoal(mode) {
        const topUpEl = document.getElementById('goalTopUpAmount');
        const currentEl = document.getElementById('goalCurrent');
        const goalIdEl = document.getElementById('goalId');
        const goalTitleEl = document.getElementById('goalTitle');
        if (!topUpEl || !currentEl) return;
        const sum = parseFloat(topUpEl.value);
        if (!sum || sum <= 0) {
            (tg?.showAlert ? tg.showAlert('Введите сумму пополнения') : alert('Введите сумму пополнения'));
            return;
        }
        const prev = parseFloat(currentEl.value) || 0;
        const next = prev + sum;
        currentEl.value = next.toFixed(2);
        topUpEl.value = '';
        const id = goalIdEl?.value?.trim();
        const goalTitle = goalTitleEl?.value?.trim() || 'Цель';
        try {
            if (id) {
                await API.request('PATCH', `/api/finance/goals/${id}`, { current_amount: next });
            }
            if (mode === 'defer') {
                await API.request('POST', '/api/finance/transactions', {
                    type: 'savings',
                    date: Utils.today(),
                    amount: sum,
                    category: 'Сбережения в копилку',
                    comment: goalTitle
                });
            } else if (mode === 'balance') {
                await API.request('POST', '/api/finance/transactions', {
                    type: 'expense',
                    date: Utils.today(),
                    amount: sum,
                    category: 'В цель',
                    comment: goalTitle
                });
            }
            await this.load();
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        } catch (e) {
            console.error('Goal top-up error:', e);
            currentEl.value = prev.toFixed(2);
            if (tg?.showAlert) tg.showAlert(e.message || 'Ошибка пополнения'); else alert(e.message);
        }
    },

    async deleteGoal() {
        const id = document.getElementById('goalId').value.trim();
        if (!id) return;
        const doDelete = async () => {
            try {
                await API.request('DELETE', `/api/finance/goals/${id}`);
                this.closeGoalModal();
                await this.load();
                if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
            } catch (e) {
                console.error('Finance goal delete error:', e);
                if (tg?.showAlert) tg.showAlert(e.message || 'Ошибка удаления'); else alert(e.message);
            }
        };
        if (tg?.showConfirm) tg.showConfirm('Удалить цель?', ok => { if (ok) doDelete(); });
        else if (confirm('Удалить цель?')) doDelete();
    },
    
    closeGoalModal() {
        const modal = document.getElementById('financeGoalModal');
        if (modal) modal.classList.remove('open');
    },
    
    async saveGoal() {
        const id = document.getElementById('goalId').value.trim();
        const title = document.getElementById('goalTitle').value.trim();
        const targetStr = document.getElementById('goalTarget').value;
        const currentStr = document.getElementById('goalCurrent').value || '0';
        const target_date = document.getElementById('goalDate').value || null;
        const priority = parseInt(document.getElementById('goalPriority').value) || 1;
        
        if (!title) {
            return (tg?.showAlert ? tg.showAlert('Введите название цели') : alert('Введите название цели'));
        }
        const target_amount = parseFloat(targetStr);
        const current_amount = parseFloat(currentStr) || 0;
        if (!target_amount || target_amount <= 0) {
            return (tg?.showAlert ? tg.showAlert('Введите корректную целевую сумму') : alert('Введите корректную целевую сумму'));
        }
        
        const payload = { title, target_amount, current_amount, target_date, priority };
        try {
            if (id) {
                await API.request('PATCH', `/api/finance/goals/${id}`, payload);
            } else {
                await API.request('POST', '/api/finance/goals', payload);
            }
            this.closeGoalModal();
            await this.load();
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        } catch (e) {
            console.error('Finance goal save error:', e);
            const msg = e.message || 'Ошибка сохранения цели';
            if (tg?.showAlert) tg.showAlert(msg); else alert(msg);
        }
    },

    async loadLimits() {
        try {
            const data = await API.request('GET', '/api/finance/limits');
            financeLimits = Array.isArray(data) ? data : [];
        } catch (e) {
            console.error('Finance limits load error:', e);
            financeLimits = [];
        }
    },

    async openLimitsModal() {
        await this.loadLimits();
        this.cancelLimitForm();
        this.renderLimitsList();
        const modal = document.getElementById('financeLimitsModal');
        if (modal) modal.classList.add('open');
    },

    closeLimitsModal() {
        const modal = document.getElementById('financeLimitsModal');
        if (modal) modal.classList.remove('open');
    },

    renderLimitsList() {
        const listEl = document.getElementById('financeLimitsList');
        const formWrap = document.getElementById('financeLimitsForm');
        const listWrap = document.getElementById('financeLimitsListWrap');
        if (!listEl || !listWrap) return;
        const arr = (financeSummary && financeSummary.expenses_by_category) ? financeSummary.expenses_by_category : [];
        const byCat = {};
        arr.forEach(r => { byCat[r.category] = (r.total != null ? r.total : 0); });
        if (financeLimits.length === 0) {
            listEl.innerHTML = '<p class="finance-limits-empty">Лимиты не заданы. Добавьте лимит по категории расходов.</p>';
        } else {
            listEl.innerHTML = financeLimits.map(l => {
                const spent = typeof byCat[l.category] === 'number' ? byCat[l.category] : 0;
                const limit = parseFloat(l.amount) || 0;
                const pct = limit > 0 ? Math.min(100, (spent / limit) * 100) : 0;
                const over = spent > limit;
                return `
                    <div class="finance-limit-row" data-limit-id="${l.id}">
                        <div class="finance-limit-info">
                            <span class="finance-limit-cat">${Utils.escape(l.category)}</span>
                            <span class="finance-limit-amounts">${Number(spent).toFixed(0)} / ${Number(limit).toFixed(0)} ₽</span>
                            <div class="finance-limit-bar"><div class="finance-limit-fill ${over ? 'over' : ''}" style="width:${pct}%"></div></div>
                        </div>
                        <div class="finance-limit-actions">
                            <button type="button" class="btn-icon" onclick="Finance.openEditLimit(${l.id})" title="Изменить">✏️</button>
                            <button type="button" class="btn-icon btn-danger" onclick="Finance.deleteLimit(${l.id})" title="Удалить">🗑</button>
                        </div>
                    </div>
                `;
            }).join('');
        }
        if (formWrap) formWrap.style.display = 'none';
        listWrap.style.display = 'block';
    },

    showAddLimitForm() {
        document.getElementById('limitId').value = '';
        document.getElementById('limitCategory').value = '';
        document.getElementById('limitAmount').value = '';
        document.getElementById('financeLimitsForm').style.display = 'block';
        document.getElementById('financeLimitsListWrap').style.display = 'none';
    },

    cancelLimitForm() {
        const form = document.getElementById('financeLimitsForm');
        const listWrap = document.getElementById('financeLimitsListWrap');
        if (form) form.style.display = 'none';
        if (listWrap) listWrap.style.display = 'block';
    },

    openEditLimit(id) {
        const l = financeLimits.find(x => x.id === id);
        if (!l) return;
        document.getElementById('limitId').value = l.id;
        document.getElementById('limitCategory').value = l.category || '';
        document.getElementById('limitAmount').value = l.amount != null ? l.amount : '';
        document.getElementById('financeLimitsForm').style.display = 'block';
        document.getElementById('financeLimitsListWrap').style.display = 'none';
    },

    async saveLimit() {
        const id = document.getElementById('limitId').value.trim();
        const category = document.getElementById('limitCategory').value.trim();
        const amount = parseFloat(document.getElementById('limitAmount').value);
        if (!category) {
            (tg?.showAlert || alert)('Введите категорию');
            return;
        }
        if (!amount || amount <= 0) {
            (tg?.showAlert || alert)('Введите сумму лимита');
            return;
        }
        try {
            if (id) {
                await API.request('PATCH', `/api/finance/limits/${id}`, { category, amount });
            } else {
                await API.request('POST', '/api/finance/limits', { category, amount });
            }
            await this.loadLimits();
            this.renderLimitsList();
            this.cancelLimitForm();
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        } catch (e) {
            console.error('Finance limit save error:', e);
            (tg?.showAlert || alert)(e.message || 'Ошибка сохранения лимита');
        }
    },

    async deleteLimit(id) {
        const doDelete = async () => {
            try {
                await API.request('DELETE', `/api/finance/limits/${id}`);
                await this.loadLimits();
                this.renderLimitsList();
                if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
            } catch (e) {
                console.error('Finance limit delete error:', e);
                (tg?.showAlert || alert)(e.message || 'Ошибка удаления');
            }
        };
        if (tg?.showConfirm) tg.showConfirm('Удалить лимит?', ok => { if (ok) doDelete(); });
        else if (confirm('Удалить лимит?')) doDelete();
    }
};
