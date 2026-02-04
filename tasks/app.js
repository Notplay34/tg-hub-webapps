/**
 * Telegram Web App — Список дел
 * Синхронизация через API
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
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': userId
            }
        };
        if (data) options.body = JSON.stringify(data);
        
        const response = await fetch(API_URL + endpoint, options);
        if (!response.ok) throw new Error('API Error');
        return await response.json();
    },
    
    getTasks() { return this.request('GET', '/api/tasks'); },
    createTask(task) { return this.request('POST', '/api/tasks', task); },
    updateTask(id, data) { return this.request('PATCH', `/api/tasks/${id}`, data); },
    deleteTask(id) { return this.request('DELETE', `/api/tasks/${id}`); }
};

// === Утилиты ===
const DateUtils = {
    today() { return new Date().toISOString().split('T')[0]; },
    tomorrow() {
        const d = new Date();
        d.setDate(d.getDate() + 1);
        return d.toISOString().split('T')[0];
    },
    format(dateStr) {
        if (!dateStr) return '';
        if (dateStr === this.today()) return 'Сегодня';
        if (dateStr === this.tomorrow()) return 'Завтра';
        return new Date(dateStr).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
    },
    isOverdue(dateStr) { return dateStr && dateStr < this.today(); },
    isToday(dateStr) { return dateStr === this.today(); }
};

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// === DOM ===
const DOM = {
    taskList: document.getElementById('taskList'),
    emptyState: document.getElementById('emptyState'),
    modal: document.getElementById('modal'),
    modalTitle: document.getElementById('modalTitle'),
    modalClose: document.getElementById('modalClose'),
    btnAdd: document.getElementById('btnAdd'),
    taskForm: document.getElementById('taskForm'),
    filters: document.querySelectorAll('.filter'),
    taskId: document.getElementById('taskId'),
    title: document.getElementById('title'),
    description: document.getElementById('description'),
    deadline: document.getElementById('deadline'),
    priority: document.getElementById('priority')
};

let currentFilter = 'all';
let tasksCache = [];

// === Загрузка ===
async function loadTasks() {
    try {
        tasksCache = await API.getTasks();
    } catch (e) {
        console.error('Load error:', e);
        tasksCache = [];
    }
}

function filterTasks(tasks, filter) {
    switch (filter) {
        case 'today': return tasks.filter(t => !t.done && t.deadline === DateUtils.today());
        case 'tomorrow': return tasks.filter(t => !t.done && t.deadline === DateUtils.tomorrow());
        case 'high': return tasks.filter(t => !t.done && t.priority === 'high');
        case 'done': return tasks.filter(t => t.done);
        default: return tasks.filter(t => !t.done);
    }
}

function renderTask(task) {
    const deadlineClass = task.deadline 
        ? (DateUtils.isOverdue(task.deadline) ? 'overdue' : (DateUtils.isToday(task.deadline) ? 'today' : ''))
        : '';
    const priorityLabels = { high: 'Высокий', medium: 'Средний', low: 'Низкий' };
    
    return `
        <div class="task ${task.done ? 'done' : ''}" data-id="${task.id}">
            <div class="task-header">
                <div class="task-checkbox" onclick="toggleTask(${task.id})"></div>
                <div class="task-content">
                    <div class="task-title">${escapeHtml(task.title)}</div>
                    ${task.description ? `<div class="task-description">${escapeHtml(task.description)}</div>` : ''}
                    <div class="task-meta">
                        ${task.deadline ? `<span class="task-deadline ${deadlineClass}">📅 ${DateUtils.format(task.deadline)}</span>` : ''}
                        <span class="task-priority ${task.priority}">${priorityLabels[task.priority] || 'Средний'}</span>
                    </div>
                </div>
            </div>
            <div class="task-actions">
                <button class="task-btn edit" onclick="editTask(${task.id})">Изменить</button>
                <button class="task-btn delete" onclick="deleteTask(${task.id})">Удалить</button>
            </div>
        </div>
    `;
}

async function renderTasks() {
    await loadTasks();
    const tasks = filterTasks(tasksCache, currentFilter);
    
    if (tasks.length === 0) {
        DOM.taskList.innerHTML = '';
        DOM.emptyState.classList.add('show');
    } else {
        DOM.emptyState.classList.remove('show');
        DOM.taskList.innerHTML = tasks.map(renderTask).join('');
    }
}

// === Действия ===
function openModal(task = null) {
    DOM.modal.classList.add('open');
    if (task) {
        DOM.modalTitle.textContent = 'Редактирование';
        DOM.taskId.value = task.id;
        DOM.title.value = task.title;
        DOM.description.value = task.description || '';
        DOM.deadline.value = task.deadline || '';
        DOM.priority.value = task.priority || 'medium';
    } else {
        DOM.modalTitle.textContent = 'Новая задача';
        DOM.taskForm.reset();
        DOM.taskId.value = '';
        DOM.deadline.value = DateUtils.today();
    }
    DOM.title.focus();
}

function closeModal() { DOM.modal.classList.remove('open'); }

async function toggleTask(id) {
    const task = tasksCache.find(t => t.id === id);
    if (!task) return;
    
    try {
        await API.updateTask(id, { done: !task.done });
        await renderTasks();
        if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
    } catch (e) {
        console.error('Toggle error:', e);
    }
}

function editTask(id) {
    const task = tasksCache.find(t => t.id === id);
    if (task) openModal(task);
}

async function deleteTask(id) {
    const doDelete = async () => {
        try {
            await API.deleteTask(id);
            await renderTasks();
        } catch (e) {
            console.error('Delete error:', e);
        }
    };
    
    if (tg?.showConfirm) {
        tg.showConfirm('Удалить задачу?', async (ok) => { if (ok) await doDelete(); });
    } else if (confirm('Удалить задачу?')) {
        await doDelete();
    }
}

// === События ===
DOM.btnAdd.addEventListener('click', () => openModal());
DOM.modalClose.addEventListener('click', closeModal);
DOM.modal.addEventListener('click', (e) => { if (e.target === DOM.modal) closeModal(); });

DOM.taskForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const data = {
        title: DOM.title.value.trim(),
        description: DOM.description.value.trim(),
        deadline: DOM.deadline.value || null,
        priority: DOM.priority.value
    };
    
    const id = DOM.taskId.value;
    
    try {
        if (id) {
            await API.updateTask(parseInt(id), data);
        } else {
            await API.createTask(data);
        }
        closeModal();
        await renderTasks();
        if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
    } catch (e) {
        console.error('Save error:', e);
        alert('Ошибка сохранения');
    }
});

DOM.filters.forEach(btn => {
    btn.addEventListener('click', () => {
        DOM.filters.forEach(f => f.classList.remove('active'));
        btn.classList.add('active');
        currentFilter = btn.dataset.filter;
        renderTasks();
    });
});

// === Инициализация ===
renderTasks();
