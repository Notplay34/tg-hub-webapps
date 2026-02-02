/**
 * Telegram Web App — Список дел
 */

const tg = window.Telegram?.WebApp;

if (tg) {
    tg.ready();
    tg.expand();
    if (tg.colorScheme === 'dark') {
        document.body.classList.add('theme-dark');
    }
    tg.setHeaderColor('secondary_bg_color');
}

// Хранилище
const Storage = {
    KEY: 'tg_hub_tasks',
    
    getAll() {
        const data = localStorage.getItem(this.KEY);
        return data ? JSON.parse(data) : [];
    },
    
    save(tasks) {
        localStorage.setItem(this.KEY, JSON.stringify(tasks));
    },
    
    add(task) {
        const tasks = this.getAll();
        task.id = Date.now();
        task.createdAt = new Date().toISOString();
        task.done = false;
        tasks.unshift(task);
        this.save(tasks);
        return task;
    },
    
    update(id, updates) {
        const tasks = this.getAll();
        const index = tasks.findIndex(t => t.id === id);
        if (index !== -1) {
            tasks[index] = { ...tasks[index], ...updates };
            this.save(tasks);
            return tasks[index];
        }
        return null;
    },
    
    delete(id) {
        const tasks = this.getAll();
        this.save(tasks.filter(t => t.id !== id));
    },
    
    toggle(id) {
        const tasks = this.getAll();
        const task = tasks.find(t => t.id === id);
        if (task) {
            task.done = !task.done;
            this.save(tasks);
            return task;
        }
        return null;
    }
};

// Утилиты дат
const DateUtils = {
    today() {
        return new Date().toISOString().split('T')[0];
    },
    
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
    
    isOverdue(dateStr) {
        return dateStr && dateStr < this.today();
    },
    
    isToday(dateStr) {
        return dateStr === this.today();
    }
};

// DOM
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

// Фильтрация
function filterTasks(tasks, filter) {
    switch (filter) {
        case 'today': return tasks.filter(t => !t.done && t.deadline === DateUtils.today());
        case 'tomorrow': return tasks.filter(t => !t.done && t.deadline === DateUtils.tomorrow());
        case 'high': return tasks.filter(t => !t.done && t.priority === 'high');
        case 'done': return tasks.filter(t => t.done);
        default: return tasks.filter(t => !t.done);
    }
}

// Рендер задачи
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
                        <span class="task-priority ${task.priority}">${priorityLabels[task.priority]}</span>
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

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderTasks() {
    const tasks = filterTasks(Storage.getAll(), currentFilter);
    
    if (tasks.length === 0) {
        DOM.taskList.innerHTML = '';
        DOM.emptyState.classList.add('show');
    } else {
        DOM.emptyState.classList.remove('show');
        DOM.taskList.innerHTML = tasks.map(renderTask).join('');
    }
}

function openModal(task = null) {
    DOM.modal.classList.add('open');
    
    if (task) {
        DOM.modalTitle.textContent = 'Редактирование';
        DOM.taskId.value = task.id;
        DOM.title.value = task.title;
        DOM.description.value = task.description || '';
        DOM.deadline.value = task.deadline || '';
        DOM.priority.value = task.priority;
    } else {
        DOM.modalTitle.textContent = 'Новая задача';
        DOM.taskForm.reset();
        DOM.taskId.value = '';
        DOM.deadline.value = DateUtils.today();
    }
    
    DOM.title.focus();
}

function closeModal() {
    DOM.modal.classList.remove('open');
}

function toggleTask(id) {
    Storage.toggle(id);
    renderTasks();
    if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

function editTask(id) {
    const task = Storage.getAll().find(t => t.id === id);
    if (task) openModal(task);
}

function deleteTask(id) {
    if (tg?.showConfirm) {
        tg.showConfirm('Удалить задачу?', (confirmed) => {
            if (confirmed) {
                Storage.delete(id);
                renderTasks();
            }
        });
    } else if (confirm('Удалить задачу?')) {
        Storage.delete(id);
        renderTasks();
    }
}

// События
DOM.btnAdd.addEventListener('click', () => openModal());
DOM.modalClose.addEventListener('click', closeModal);
DOM.modal.addEventListener('click', (e) => { if (e.target === DOM.modal) closeModal(); });

DOM.taskForm.addEventListener('submit', (e) => {
    e.preventDefault();
    
    const taskData = {
        title: DOM.title.value.trim(),
        description: DOM.description.value.trim(),
        deadline: DOM.deadline.value,
        priority: DOM.priority.value
    };
    
    const id = DOM.taskId.value;
    if (id) {
        Storage.update(parseInt(id), taskData);
    } else {
        Storage.add(taskData);
    }
    
    closeModal();
    renderTasks();
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
});

DOM.filters.forEach(btn => {
    btn.addEventListener('click', () => {
        DOM.filters.forEach(f => f.classList.remove('active'));
        btn.classList.add('active');
        currentFilter = btn.dataset.filter;
        renderTasks();
    });
});

document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

// Инициализация
renderTasks();
