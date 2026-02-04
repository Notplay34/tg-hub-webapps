/**
 * Telegram Web App — Картотека
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
    
    getPeople() { return this.request('GET', '/api/people'); },
    createPerson(person) { return this.request('POST', '/api/people', person); },
    updatePerson(id, person) { return this.request('PATCH', `/api/people/${id}`, person); },
    deletePerson(id) { return this.request('DELETE', `/api/people/${id}`); },
    addNote(personId, text) { return this.request('POST', `/api/people/${personId}/notes`, { text }); },
    deleteNote(personId, noteId) { return this.request('DELETE', `/api/people/${personId}/notes/${noteId}`); }
};

// === Утилиты ===
function getInitials(fio) {
    if (!fio) return '?';
    const parts = fio.split(' ').filter(p => p);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return fio.substring(0, 2).toUpperCase();
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    return new Date(dateStr).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
}

function formatNoteDate(dateStr) {
    return new Date(dateStr).toLocaleDateString('ru-RU', {
        day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
    });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

const financialLabels = { low: 'Низкое', medium: 'Среднее', high: 'Высокое', wealthy: 'Состоятельный' };

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

let currentPersonId = null;
let currentFilter = 'all';
let editGroups = [];
let editConnections = [];
let peopleCache = [];

// === Загрузка ===
async function loadPeople() {
    try {
        peopleCache = await API.getPeople();
    } catch (e) {
        console.error('Load error:', e);
        peopleCache = [];
    }
}

function getAllGroups() {
    const groups = new Set();
    peopleCache.forEach(p => {
        const data = p.data || {};
        if (data.groups) data.groups.forEach(g => groups.add(g));
    });
    return Array.from(groups).sort();
}

// === Рендер списка ===
async function renderPeopleList() {
    await loadPeople();
    let people = [...peopleCache];
    const search = DOM.searchInput.value.toLowerCase().trim();
    
    if (search) {
        people = people.filter(p => 
            p.fio.toLowerCase().includes(search) ||
            (p.data?.relation && p.data.relation.toLowerCase().includes(search)) ||
            (p.data?.workplace && p.data.workplace.toLowerCase().includes(search))
        );
    }
    
    if (currentFilter !== 'all') {
        people = people.filter(p => p.data?.groups && p.data.groups.includes(currentFilter));
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
    const data = person.data || {};
    const tagsHtml = data.groups && data.groups.length 
        ? `<div class="person-tags">${data.groups.slice(0, 3).map(g => `<span>${escapeHtml(g)}</span>`).join('')}</div>`
        : '';
    
    return `
        <div class="person-item" onclick="openPerson(${person.id})">
            <div class="person-avatar">${getInitials(person.fio)}</div>
            <div class="person-info">
                <h3>${escapeHtml(person.fio)}</h3>
                <p>${escapeHtml(data.relation || data.workplace || '')}</p>
                ${tagsHtml}
            </div>
        </div>
    `;
}

function renderGroupsFilter() {
    const groups = getAllGroups();
    let html = `<button class="group-tag ${currentFilter === 'all' ? 'active' : ''}" data-group="all">Все</button>`;
    groups.forEach(group => {
        html += `<button class="group-tag ${currentFilter === group ? 'active' : ''}" data-group="${escapeHtml(group)}">${escapeHtml(group)}</button>`;
    });
    DOM.groupsFilter.innerHTML = html;
    
    DOM.groupsFilter.querySelectorAll('.group-tag').forEach(btn => {
        btn.addEventListener('click', () => {
            currentFilter = btn.dataset.group;
            renderPeopleList();
        });
    });
}

// === Карточка человека ===
function openPerson(id) {
    const person = peopleCache.find(p => p.id === id);
    if (!person) return;
    
    currentPersonId = id;
    DOM.personName.textContent = person.fio;
    renderPersonCard(person);
    
    DOM.listScreen.classList.add('hidden');
    DOM.personScreen.classList.remove('hidden');
}

function renderPersonCard(person) {
    const data = person.data || {};
    let html = '';
    
    // Основное
    html += `
        <div class="card-section">
            <h4>Основное</h4>
            ${renderField('Дата рождения', data.birth_date ? formatDate(data.birth_date) : null)}
            ${renderField('Кем приходится', data.relation)}
            ${renderField('Место работы', data.workplace)}
            ${renderField('Финансовое состояние', data.financial ? financialLabels[data.financial] : null)}
        </div>
    `;
    
    // Характеристика
    html += `
        <div class="card-section">
            <h4>Характеристика</h4>
            ${renderField('Сильные стороны', data.strengths)}
            ${renderField('Слабые стороны', data.weaknesses)}
            ${renderField('Возможная польза', data.benefits)}
            ${renderField('Возможные проблемы', data.problems)}
        </div>
    `;
    
    // Группы
    if (data.groups && data.groups.length) {
        html += `
            <div class="card-section">
                <h4>Группы / Круги</h4>
                <div class="person-tags">
                    ${data.groups.map(g => `<span>${escapeHtml(g)}</span>`).join('')}
                </div>
            </div>
        `;
    }
    
    // Связи
    if (data.connections && data.connections.length) {
        html += `
            <div class="card-section connections-section">
                <h4>Связи</h4>
                ${data.connections.map(connId => {
                    const conn = peopleCache.find(p => p.id === connId);
                    if (!conn) return '';
                    return `
                        <div class="connection-item" onclick="openPerson(${conn.id})">
                            <div class="connection-avatar">${getInitials(conn.fio)}</div>
                            <div class="connection-info">
                                <h5>${escapeHtml(conn.fio)}</h5>
                                <span>${escapeHtml(conn.data?.relation || '')}</span>
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
                            <div class="note-date">${formatNoteDate(note.created_at)}</div>
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
        const data = person.data || {};
        DOM.editTitle.textContent = 'Редактировать';
        DOM.personId.value = person.id;
        document.getElementById('fio').value = person.fio || '';
        document.getElementById('birthDate').value = data.birth_date || '';
        document.getElementById('relation').value = data.relation || '';
        document.getElementById('workplace').value = data.workplace || '';
        document.getElementById('financial').value = data.financial || '';
        document.getElementById('strengths').value = data.strengths || '';
        document.getElementById('weaknesses').value = data.weaknesses || '';
        document.getElementById('benefits').value = data.benefits || '';
        document.getElementById('problems').value = data.problems || '';
        
        editGroups = data.groups ? [...data.groups] : [];
        editConnections = data.connections ? [...data.connections] : [];
        
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

function closeEditModal() { DOM.editModal.classList.remove('open'); }

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
    const allGroups = getAllGroups();
    const available = allGroups.filter(g => !editGroups.includes(g));
    DOM.groupsSuggestions.innerHTML = available.slice(0, 5).map(g => 
        `<span class="tag-suggestion" onclick="addGroup('${escapeHtml(g)}')">${escapeHtml(g)}</span>`
    ).join('');
}

function renderEditConnections() {
    DOM.connectionsList.innerHTML = editConnections.map(id => {
        const person = peopleCache.find(p => p.id === id);
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

function closeConnectionModal() { DOM.connectionModal.classList.remove('open'); }

function renderConnectionList() {
    const search = DOM.connectionSearch.value.toLowerCase().trim();
    let people = [...peopleCache];
    const currentId = parseInt(DOM.personId.value) || 0;
    
    people = people.filter(p => p.id !== currentId && !editConnections.includes(p.id));
    
    if (search) {
        people = people.filter(p => p.fio.toLowerCase().includes(search));
    }
    
    DOM.connectionSelectList.innerHTML = people.slice(0, 20).map(p => `
        <div class="connection-select-item" onclick="selectConnection(${p.id})">
            <div class="connection-avatar">${getInitials(p.fio)}</div>
            <div class="connection-info">
                <h5>${escapeHtml(p.fio)}</h5>
                <span>${escapeHtml(p.data?.relation || '')}</span>
            </div>
        </div>
    `).join('') || '<p style="text-align:center;color:var(--text-secondary);padding:20px;">Нет контактов</p>';
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

function closeNoteModal() { DOM.noteModal.classList.remove('open'); }

async function deleteNote(noteId) {
    const doDelete = async () => {
        try {
            await API.deleteNote(currentPersonId, noteId);
            await loadPeople();
            const person = peopleCache.find(p => p.id === currentPersonId);
            if (person) renderPersonCard(person);
        } catch (e) {
            console.error('Delete note error:', e);
        }
    };
    
    if (tg?.showConfirm) {
        tg.showConfirm('Удалить заметку?', async (ok) => { if (ok) await doDelete(); });
    } else if (confirm('Удалить заметку?')) {
        await doDelete();
    }
}

// === Сохранение ===
async function savePerson() {
    const id = DOM.personId.value;
    
    const personData = {
        fio: document.getElementById('fio').value.trim(),
        birth_date: document.getElementById('birthDate').value || null,
        relation: document.getElementById('relation').value.trim() || null,
        workplace: document.getElementById('workplace').value.trim() || null,
        financial: document.getElementById('financial').value || null,
        strengths: document.getElementById('strengths').value.trim() || null,
        weaknesses: document.getElementById('weaknesses').value.trim() || null,
        benefits: document.getElementById('benefits').value.trim() || null,
        problems: document.getElementById('problems').value.trim() || null,
        groups: editGroups,
        connections: editConnections
    };
    
    if (!personData.fio) {
        alert('Введите ФИО');
        return;
    }
    
    try {
        if (id) {
            await API.updatePerson(parseInt(id), personData);
        } else {
            const result = await API.createPerson(personData);
            currentPersonId = result.id;
        }
        
        closeEditModal();
        await loadPeople();
        
        if (currentPersonId) {
            const person = peopleCache.find(p => p.id === currentPersonId);
            if (person) {
                renderPersonCard(person);
                DOM.personName.textContent = person.fio;
            }
        }
        
        if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
    } catch (e) {
        console.error('Save error:', e);
        alert('Ошибка сохранения');
    }
}

async function deletePerson() {
    const id = parseInt(DOM.personId.value);
    
    const doDelete = async () => {
        try {
            await API.deletePerson(id);
            closeEditModal();
            DOM.personScreen.classList.add('hidden');
            DOM.listScreen.classList.remove('hidden');
            currentPersonId = null;
            await renderPeopleList();
        } catch (e) {
            console.error('Delete error:', e);
        }
    };
    
    if (tg?.showConfirm) {
        tg.showConfirm('Удалить контакт?', async (ok) => { if (ok) await doDelete(); });
    } else if (confirm('Удалить контакт?')) {
        await doDelete();
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
    const person = peopleCache.find(p => p.id === currentPersonId);
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
DOM.noteForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = DOM.noteText.value.trim();
    if (text) {
        try {
            await API.addNote(currentPersonId, text);
            await loadPeople();
            const person = peopleCache.find(p => p.id === currentPersonId);
            if (person) renderPersonCard(person);
            closeNoteModal();
        } catch (e) {
            console.error('Add note error:', e);
        }
    }
});

[DOM.editModal, DOM.noteModal, DOM.connectionModal].forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('open');
    });
});

// === Инициализация ===
renderPeopleList();
