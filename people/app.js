/**
 * Telegram Web App — Картотека
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

// === Хранилище ===
const Storage = {
    KEY: 'tg_hub_people',
    
    getAll() {
        const data = localStorage.getItem(this.KEY);
        return data ? JSON.parse(data) : [];
    },
    
    save(people) {
        localStorage.setItem(this.KEY, JSON.stringify(people));
    },
    
    getById(id) {
        return this.getAll().find(p => p.id === id);
    },
    
    add(person) {
        const people = this.getAll();
        person.id = Date.now();
        person.createdAt = new Date().toISOString();
        person.notes = [];
        people.unshift(person);
        this.save(people);
        return person;
    },
    
    update(id, updates) {
        const people = this.getAll();
        const index = people.findIndex(p => p.id === id);
        if (index !== -1) {
            people[index] = { ...people[index], ...updates };
            this.save(people);
            return people[index];
        }
        return null;
    },
    
    delete(id) {
        const people = this.getAll();
        this.save(people.filter(p => p.id !== id));
    },
    
    addNote(personId, text) {
        const people = this.getAll();
        const person = people.find(p => p.id === personId);
        if (person) {
            if (!person.notes) person.notes = [];
            person.notes.unshift({
                id: Date.now(),
                text,
                date: new Date().toISOString()
            });
            this.save(people);
            return person;
        }
        return null;
    },
    
    deleteNote(personId, noteId) {
        const people = this.getAll();
        const person = people.find(p => p.id === personId);
        if (person && person.notes) {
            person.notes = person.notes.filter(n => n.id !== noteId);
            this.save(people);
            return person;
        }
        return null;
    },
    
    getAllGroups() {
        const people = this.getAll();
        const groups = new Set();
        people.forEach(p => {
            if (p.groups) p.groups.forEach(g => groups.add(g));
        });
        return Array.from(groups).sort();
    }
};

// === Утилиты ===
function getInitials(fio) {
    if (!fio) return '?';
    const parts = fio.split(' ').filter(p => p);
    if (parts.length >= 2) {
        return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return fio.substring(0, 2).toUpperCase();
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('ru-RU', { 
        day: 'numeric', 
        month: 'long',
        year: 'numeric'
    });
}

function formatNoteDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('ru-RU', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

const financialLabels = {
    low: 'Низкое',
    medium: 'Среднее',
    high: 'Высокое',
    wealthy: 'Состоятельный'
};

// === DOM ===
const DOM = {
    listScreen: document.getElementById('listScreen'),
    personScreen: document.getElementById('personScreen'),
    peopleList: document.getElementById('peopleList'),
    emptyState: document.getElementById('emptyState'),
    searchInput: document.getElementById('searchInput'),
    groupsFilter: document.getElementById('groupsFilter'),
    
    personName: document.getElementById('personName'),
    personCard: document.getElementById('personCard'),
    btnBack: document.getElementById('btnBack'),
    btnEdit: document.getElementById('btnEdit'),
    btnAddPerson: document.getElementById('btnAddPerson'),
    
    editModal: document.getElementById('editModal'),
    editTitle: document.getElementById('editTitle'),
    editClose: document.getElementById('editClose'),
    btnSave: document.getElementById('btnSave'),
    btnDelete: document.getElementById('btnDelete'),
    personForm: document.getElementById('personForm'),
    personId: document.getElementById('personId'),
    
    noteModal: document.getElementById('noteModal'),
    noteClose: document.getElementById('noteClose'),
    noteForm: document.getElementById('noteForm'),
    noteText: document.getElementById('noteText'),
    
    connectionModal: document.getElementById('connectionModal'),
    connectionClose: document.getElementById('connectionClose'),
    connectionSearch: document.getElementById('connectionSearch'),
    connectionSelectList: document.getElementById('connectionSelectList'),
    
    groupsList: document.getElementById('groupsList'),
    groupInput: document.getElementById('groupInput'),
    groupsSuggestions: document.getElementById('groupsSuggestions'),
    connectionsList: document.getElementById('connectionsList'),
    btnAddConnection: document.getElementById('btnAddConnection')
};

// === State ===
let currentPersonId = null;
let currentFilter = 'all';
let editGroups = [];
let editConnections = [];

// === Рендер списка людей ===
function renderPeopleList() {
    let people = Storage.getAll();
    const search = DOM.searchInput.value.toLowerCase().trim();
    
    // Фильтр по поиску
    if (search) {
        people = people.filter(p => 
            p.fio.toLowerCase().includes(search) ||
            (p.relation && p.relation.toLowerCase().includes(search)) ||
            (p.workplace && p.workplace.toLowerCase().includes(search))
        );
    }
    
    // Фильтр по группе
    if (currentFilter !== 'all') {
        people = people.filter(p => p.groups && p.groups.includes(currentFilter));
    }
    
    if (people.length === 0) {
        DOM.peopleList.innerHTML = '';
        DOM.emptyState.classList.add('show');
    } else {
        DOM.emptyState.classList.remove('show');
        DOM.peopleList.innerHTML = people.map(renderPersonItem).join('');
    }
    
    renderGroupsFilter();
}

function renderPersonItem(person) {
    const tagsHtml = person.groups && person.groups.length 
        ? `<div class="person-tags">${person.groups.slice(0, 3).map(g => `<span>${escapeHtml(g)}</span>`).join('')}</div>`
        : '';
    
    return `
        <div class="person-item" onclick="openPerson(${person.id})">
            <div class="person-avatar">${getInitials(person.fio)}</div>
            <div class="person-info">
                <h3>${escapeHtml(person.fio)}</h3>
                <p>${escapeHtml(person.relation || person.workplace || '')}</p>
                ${tagsHtml}
            </div>
        </div>
    `;
}

function renderGroupsFilter() {
    const groups = Storage.getAllGroups();
    let html = '<button class="group-tag ' + (currentFilter === 'all' ? 'active' : '') + '" data-group="all">Все</button>';
    
    groups.forEach(group => {
        html += `<button class="group-tag ${currentFilter === group ? 'active' : ''}" data-group="${escapeHtml(group)}">${escapeHtml(group)}</button>`;
    });
    
    DOM.groupsFilter.innerHTML = html;
    
    // Bind events
    DOM.groupsFilter.querySelectorAll('.group-tag').forEach(btn => {
        btn.addEventListener('click', () => {
            currentFilter = btn.dataset.group;
            renderPeopleList();
        });
    });
}

// === Открыть карточку человека ===
function openPerson(id) {
    const person = Storage.getById(id);
    if (!person) return;
    
    currentPersonId = id;
    DOM.personName.textContent = person.fio;
    
    renderPersonCard(person);
    
    DOM.listScreen.classList.add('hidden');
    DOM.personScreen.classList.remove('hidden');
}

function renderPersonCard(person) {
    let html = '';
    
    // Основная информация
    html += `
        <div class="card-section">
            <h4>Основное</h4>
            ${renderField('Дата рождения', person.birthDate ? formatDate(person.birthDate) : null)}
            ${renderField('Кем приходится', person.relation)}
            ${renderField('Место работы', person.workplace)}
            ${renderField('Финансовое состояние', person.financial ? financialLabels[person.financial] : null)}
        </div>
    `;
    
    // Характеристика
    html += `
        <div class="card-section">
            <h4>Характеристика</h4>
            ${renderField('Сильные стороны', person.strengths)}
            ${renderField('Слабые стороны', person.weaknesses)}
            ${renderField('Возможная польза', person.benefits)}
            ${renderField('Возможные проблемы', person.problems)}
        </div>
    `;
    
    // Группы
    if (person.groups && person.groups.length) {
        html += `
            <div class="card-section">
                <h4>Группы / Круги</h4>
                <div class="person-tags">
                    ${person.groups.map(g => `<span>${escapeHtml(g)}</span>`).join('')}
                </div>
            </div>
        `;
    }
    
    // Связи
    if (person.connections && person.connections.length) {
        html += `
            <div class="card-section connections-section">
                <h4>Связи</h4>
                ${person.connections.map(connId => {
                    const conn = Storage.getById(connId);
                    if (!conn) return '';
                    return `
                        <div class="connection-item" onclick="openPerson(${conn.id})">
                            <div class="connection-avatar">${getInitials(conn.fio)}</div>
                            <div class="connection-info">
                                <h5>${escapeHtml(conn.fio)}</h5>
                                <span>${escapeHtml(conn.relation || '')}</span>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    }
    
    // Заметки
    html += `
        <div class="card-section">
            <div class="notes-header">
                <h4>Заметки</h4>
                <button class="btn-add-note" onclick="openNoteModal()">+ Добавить</button>
            </div>
            <div class="notes-list">
                ${person.notes && person.notes.length 
                    ? person.notes.map(note => `
                        <div class="note-item">
                            <div class="note-date">${formatNoteDate(note.date)}</div>
                            <div class="note-text">${escapeHtml(note.text)}</div>
                            <div class="note-actions">
                                <button class="note-delete" onclick="deleteNote(${note.id})">Удалить</button>
                            </div>
                        </div>
                    `).join('')
                    : '<p class="empty-value">Нет заметок</p>'
                }
            </div>
        </div>
    `;
    
    DOM.personCard.innerHTML = html;
}

function renderField(label, value) {
    return `
        <div class="card-field">
            <label>${label}</label>
            <p class="${value ? '' : 'empty-value'}">${escapeHtml(value) || '—'}</p>
        </div>
    `;
}

// === Редактирование ===
function openEditModal(person = null) {
    DOM.editModal.classList.add('open');
    
    if (person) {
        DOM.editTitle.textContent = 'Редактировать';
        DOM.personId.value = person.id;
        document.getElementById('fio').value = person.fio || '';
        document.getElementById('birthDate').value = person.birthDate || '';
        document.getElementById('relation').value = person.relation || '';
        document.getElementById('workplace').value = person.workplace || '';
        document.getElementById('financial').value = person.financial || '';
        document.getElementById('strengths').value = person.strengths || '';
        document.getElementById('weaknesses').value = person.weaknesses || '';
        document.getElementById('benefits').value = person.benefits || '';
        document.getElementById('problems').value = person.problems || '';
        
        editGroups = person.groups ? [...person.groups] : [];
        editConnections = person.connections ? [...person.connections] : [];
        
        DOM.btnDelete.style.display = 'block';
    } else {
        DOM.editTitle.textContent = 'Новый контакт';
        DOM.personForm.reset();
        DOM.personId.value = '';
        editGroups = [];
        editConnections = [];
        DOM.btnDelete.style.display = 'none';
    }
    
    renderEditGroups();
    renderEditConnections();
    renderGroupSuggestions();
}

function closeEditModal() {
    DOM.editModal.classList.remove('open');
}

function renderEditGroups() {
    DOM.groupsList.innerHTML = editGroups.map(g => `
        <span class="tag">${escapeHtml(g)} <span class="tag-remove" onclick="removeGroup('${escapeHtml(g)}')">&times;</span></span>
    `).join('');
}

function addGroup(group) {
    group = group.trim();
    if (group && !editGroups.includes(group)) {
        editGroups.push(group);
        renderEditGroups();
        renderGroupSuggestions();
    }
    DOM.groupInput.value = '';
}

function removeGroup(group) {
    editGroups = editGroups.filter(g => g !== group);
    renderEditGroups();
    renderGroupSuggestions();
}

function renderGroupSuggestions() {
    const allGroups = Storage.getAllGroups();
    const available = allGroups.filter(g => !editGroups.includes(g));
    
    DOM.groupsSuggestions.innerHTML = available.slice(0, 5).map(g => 
        `<span class="tag-suggestion" onclick="addGroup('${escapeHtml(g)}')">${escapeHtml(g)}</span>`
    ).join('');
}

function renderEditConnections() {
    DOM.connectionsList.innerHTML = editConnections.map(id => {
        const person = Storage.getById(id);
        if (!person) return '';
        return `
            <div class="connection-edit-item">
                <div class="connection-avatar">${getInitials(person.fio)}</div>
                <span>${escapeHtml(person.fio)}</span>
                <button class="connection-remove" onclick="removeConnection(${id})">&times;</button>
            </div>
        `;
    }).join('');
}

function removeConnection(id) {
    editConnections = editConnections.filter(c => c !== id);
    renderEditConnections();
}

// === Связи ===
function openConnectionModal() {
    DOM.connectionModal.classList.add('open');
    DOM.connectionSearch.value = '';
    renderConnectionList();
}

function closeConnectionModal() {
    DOM.connectionModal.classList.remove('open');
}

function renderConnectionList() {
    const search = DOM.connectionSearch.value.toLowerCase().trim();
    let people = Storage.getAll();
    const currentId = parseInt(DOM.personId.value) || 0;
    
    // Исключаем текущего человека и уже добавленные связи
    people = people.filter(p => p.id !== currentId && !editConnections.includes(p.id));
    
    if (search) {
        people = people.filter(p => p.fio.toLowerCase().includes(search));
    }
    
    DOM.connectionSelectList.innerHTML = people.slice(0, 20).map(p => `
        <div class="connection-select-item" onclick="selectConnection(${p.id})">
            <div class="connection-avatar">${getInitials(p.fio)}</div>
            <div class="connection-info">
                <h5>${escapeHtml(p.fio)}</h5>
                <span>${escapeHtml(p.relation || '')}</span>
            </div>
        </div>
    `).join('') || '<p style="text-align:center;color:var(--text-secondary);padding:20px;">Нет доступных контактов</p>';
}

function selectConnection(id) {
    if (!editConnections.includes(id)) {
        editConnections.push(id);
        renderEditConnections();
    }
    closeConnectionModal();
}

// === Заметки ===
function openNoteModal() {
    DOM.noteModal.classList.add('open');
    DOM.noteText.value = '';
    DOM.noteText.focus();
}

function closeNoteModal() {
    DOM.noteModal.classList.remove('open');
}

function deleteNote(noteId) {
    if (tg?.showConfirm) {
        tg.showConfirm('Удалить заметку?', (confirmed) => {
            if (confirmed) {
                const person = Storage.deleteNote(currentPersonId, noteId);
                if (person) renderPersonCard(person);
            }
        });
    } else if (confirm('Удалить заметку?')) {
        const person = Storage.deleteNote(currentPersonId, noteId);
        if (person) renderPersonCard(person);
    }
}

// === Сохранение ===
function savePerson() {
    const id = DOM.personId.value;
    
    const personData = {
        fio: document.getElementById('fio').value.trim(),
        birthDate: document.getElementById('birthDate').value,
        relation: document.getElementById('relation').value.trim(),
        workplace: document.getElementById('workplace').value.trim(),
        financial: document.getElementById('financial').value,
        strengths: document.getElementById('strengths').value.trim(),
        weaknesses: document.getElementById('weaknesses').value.trim(),
        benefits: document.getElementById('benefits').value.trim(),
        problems: document.getElementById('problems').value.trim(),
        groups: editGroups,
        connections: editConnections
    };
    
    if (!personData.fio) {
        alert('Введите ФИО');
        return;
    }
    
    if (id) {
        Storage.update(parseInt(id), personData);
        const person = Storage.getById(parseInt(id));
        renderPersonCard(person);
        DOM.personName.textContent = person.fio;
    } else {
        const newPerson = Storage.add(personData);
        currentPersonId = newPerson.id;
        openPerson(newPerson.id);
    }
    
    closeEditModal();
    renderPeopleList();
    
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
}

function deletePerson() {
    const id = parseInt(DOM.personId.value);
    
    const doDelete = () => {
        Storage.delete(id);
        closeEditModal();
        DOM.personScreen.classList.add('hidden');
        DOM.listScreen.classList.remove('hidden');
        currentPersonId = null;
        renderPeopleList();
    };
    
    if (tg?.showConfirm) {
        tg.showConfirm('Удалить контакт?', (confirmed) => {
            if (confirmed) doDelete();
        });
    } else if (confirm('Удалить контакт?')) {
        doDelete();
    }
}

// === События ===
DOM.btnAddPerson.addEventListener('click', () => openEditModal());
DOM.btnBack.addEventListener('click', () => {
    DOM.personScreen.classList.add('hidden');
    DOM.listScreen.classList.remove('hidden');
    currentPersonId = null;
});
DOM.btnEdit.addEventListener('click', () => {
    const person = Storage.getById(currentPersonId);
    if (person) openEditModal(person);
});

DOM.editClose.addEventListener('click', closeEditModal);
DOM.btnSave.addEventListener('click', savePerson);
DOM.btnDelete.addEventListener('click', deletePerson);

DOM.searchInput.addEventListener('input', renderPeopleList);

DOM.groupInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        addGroup(DOM.groupInput.value);
    }
});

DOM.btnAddConnection.addEventListener('click', openConnectionModal);
DOM.connectionClose.addEventListener('click', closeConnectionModal);
DOM.connectionSearch.addEventListener('input', renderConnectionList);

DOM.noteClose.addEventListener('click', closeNoteModal);
DOM.noteForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = DOM.noteText.value.trim();
    if (text) {
        const person = Storage.addNote(currentPersonId, text);
        if (person) renderPersonCard(person);
        closeNoteModal();
    }
});

// Закрытие модалов по клику вне
[DOM.editModal, DOM.noteModal, DOM.connectionModal].forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('open');
        }
    });
});

// === Инициализация ===
renderPeopleList();
