/**
 * Telegram Web App — База знаний
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
    
    getAll() { return this.request('GET', '/api/knowledge'); },
    create(item) { return this.request('POST', '/api/knowledge', item); },
    update(id, item) { return this.request('PATCH', `/api/knowledge/${id}`, item); },
    delete(id) { return this.request('DELETE', `/api/knowledge/${id}`); }
};

// === Утилиты ===
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateStr) {
    return new Date(dateStr).toLocaleDateString('ru-RU', {
        day: 'numeric', month: 'long', year: 'numeric'
    });
}

// === DOM ===
const DOM = {
    notesList: document.getElementById('notesList'),
    emptyState: document.getElementById('emptyState'),
    searchInput: document.getElementById('searchInput'),
    tagsFilter: document.getElementById('tagsFilter'),
    btnAdd: document.getElementById('btnAdd'),
    
    viewModal: document.getElementById('viewModal'),
    viewTitle: document.getElementById('viewTitle'),
    viewContent: document.getElementById('viewContent'),
    viewTags: document.getElementById('viewTags'),
    viewDate: document.getElementById('viewDate'),
    viewClose: document.getElementById('viewClose'),
    btnEdit: document.getElementById('btnEdit'),
    btnDelete: document.getElementById('btnDelete'),
    
    editModal: document.getElementById('editModal'),
    editTitle: document.getElementById('editTitle'),
    editClose: document.getElementById('editClose'),
    btnSave: document.getElementById('btnSave'),
    noteForm: document.getElementById('noteForm'),
    noteId: document.getElementById('noteId'),
    title: document.getElementById('title'),
    content: document.getElementById('content'),
    tagsList: document.getElementById('tagsList'),
    tagInput: document.getElementById('tagInput')
};

let currentFilter = 'all';
let currentNoteId = null;
let editTags = [];
let notesCache = [];

// === Загрузка ===
async function loadNotes() {
    try {
        notesCache = await API.getAll();
    } catch (e) {
        console.error('Load error:', e);
        notesCache = [];
    }
}

function getAllTags() {
    const tags = new Set();
    notesCache.forEach(n => {
        if (n.tags) n.tags.forEach(t => tags.add(t));
    });
    return Array.from(tags).sort();
}

// === Рендер ===
async function renderNotes() {
    await loadNotes();
    let notes = [...notesCache];
    const search = DOM.searchInput.value.toLowerCase().trim();
    
    if (search) {
        notes = notes.filter(n => 
            n.title.toLowerCase().includes(search) ||
            (n.content && n.content.toLowerCase().includes(search))
        );
    }
    
    if (currentFilter !== 'all') {
        notes = notes.filter(n => n.tags && n.tags.includes(currentFilter));
    }
    
    if (notes.length === 0) {
        DOM.notesList.innerHTML = '';
        DOM.emptyState.classList.add('show');
    } else {
        DOM.emptyState.classList.remove('show');
        DOM.notesList.innerHTML = notes.map(n => `
            <div class="note-item" onclick="viewNote(${n.id})">
                <h3>${escapeHtml(n.title)}</h3>
                ${n.content ? `<p>${escapeHtml(n.content)}</p>` : ''}
                ${n.tags && n.tags.length ? `
                    <div class="note-tags">
                        ${n.tags.map(t => `<span>${escapeHtml(t)}</span>`).join('')}
                    </div>
                ` : ''}
            </div>
        `).join('');
    }
    
    renderTagsFilter();
}

function renderTagsFilter() {
    const tags = getAllTags();
    let html = `<button class="tag-btn ${currentFilter === 'all' ? 'active' : ''}" data-tag="all">Все</button>`;
    tags.forEach(tag => {
        html += `<button class="tag-btn ${currentFilter === tag ? 'active' : ''}" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>`;
    });
    DOM.tagsFilter.innerHTML = html;
    
    DOM.tagsFilter.querySelectorAll('.tag-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentFilter = btn.dataset.tag;
            renderNotes();
        });
    });
}

function renderEditTags() {
    DOM.tagsList.innerHTML = editTags.map(t => `
        <span class="tag">${escapeHtml(t)} <span class="tag-remove" onclick="removeTag('${escapeHtml(t)}')">&times;</span></span>
    `).join('');
}

function addTag(tag) {
    tag = tag.trim();
    if (tag && !editTags.includes(tag)) {
        editTags.push(tag);
        renderEditTags();
    }
    DOM.tagInput.value = '';
}

function removeTag(tag) {
    editTags = editTags.filter(t => t !== tag);
    renderEditTags();
}

// === Просмотр ===
function viewNote(id) {
    const note = notesCache.find(n => n.id === id);
    if (!note) return;
    
    currentNoteId = id;
    DOM.viewTitle.textContent = note.title;
    DOM.viewContent.textContent = note.content || '';
    DOM.viewTags.innerHTML = note.tags ? note.tags.map(t => `<span>${escapeHtml(t)}</span>`).join('') : '';
    DOM.viewDate.textContent = formatDate(note.created_at);
    DOM.viewModal.classList.add('open');
}

function closeViewModal() {
    DOM.viewModal.classList.remove('open');
    currentNoteId = null;
}

// === Редактирование ===
function openEditModal(note = null) {
    DOM.editModal.classList.add('open');
    
    if (note) {
        DOM.editTitle.textContent = 'Редактировать';
        DOM.noteId.value = note.id;
        DOM.title.value = note.title;
        DOM.content.value = note.content || '';
        editTags = note.tags ? [...note.tags] : [];
    } else {
        DOM.editTitle.textContent = 'Новая запись';
        DOM.noteForm.reset();
        DOM.noteId.value = '';
        editTags = [];
    }
    
    renderEditTags();
    DOM.title.focus();
}

function closeEditModal() {
    DOM.editModal.classList.remove('open');
}

async function saveNote() {
    const data = {
        title: DOM.title.value.trim(),
        content: DOM.content.value.trim(),
        tags: editTags
    };
    
    if (!data.title) {
        alert('Введите заголовок');
        return;
    }
    
    const id = DOM.noteId.value;
    
    try {
        if (id) {
            await API.update(parseInt(id), data);
        } else {
            await API.create(data);
        }
        closeEditModal();
        closeViewModal();
        await renderNotes();
        if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
    } catch (e) {
        console.error('Save error:', e);
        alert('Ошибка сохранения');
    }
}

async function deleteNote() {
    const doDelete = async () => {
        try {
            await API.delete(currentNoteId);
            closeViewModal();
            await renderNotes();
        } catch (e) {
            console.error('Delete error:', e);
        }
    };
    
    if (tg?.showConfirm) {
        tg.showConfirm('Удалить запись?', async (ok) => { if (ok) await doDelete(); });
    } else if (confirm('Удалить запись?')) {
        await doDelete();
    }
}

// === События ===
DOM.btnAdd.addEventListener('click', () => openEditModal());
DOM.viewClose.addEventListener('click', closeViewModal);
DOM.editClose.addEventListener('click', closeEditModal);
DOM.btnSave.addEventListener('click', saveNote);
DOM.btnEdit.addEventListener('click', () => {
    const note = notesCache.find(n => n.id === currentNoteId);
    if (note) {
        closeViewModal();
        openEditModal(note);
    }
});
DOM.btnDelete.addEventListener('click', deleteNote);
DOM.searchInput.addEventListener('input', renderNotes);
DOM.tagInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
        e.preventDefault();
        addTag(DOM.tagInput.value);
    }
});

[DOM.viewModal, DOM.editModal].forEach(modal => {
    modal.addEventListener('click', e => {
        if (e.target === modal) modal.classList.remove('open');
    });
});

// === Инициализация ===
renderNotes();
