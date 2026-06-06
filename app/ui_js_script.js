let people = [];
        let currentPerson = null;
        let isAlphabetMode = false;
        let activeMenu = null;
        let showUnmatched = false;
        let showHidden = false;
        let showHiddenPhotos = false;
        let showDevOptions = false;
        let minPhotosEnabled = false;
        let minPhotosCount = 2;
        let currentPhotoContext = null;
        let currentSortMode = 'names_asc';
        let renameContext = null;
        let lightboxPhotos = [];
        // F2 sort/filter: allPersonPhotos is the full per-person list; lightboxPhotos
        // (used by the grid AND the lightbox) is the sorted+filtered view of it.
        let allPersonPhotos = [];
        let currentPhotoSort = 'default';
        let photoFilter = { exts: null, pathText: '' };  // exts null = all extensions
        // Grouping (F2): 'none' or a mode like 'folder' / 'date_month' / 'device'.
        // gridGroups is the laid-out group descriptors (null = flat grid). collapsedGroups
        // holds the keys of collapsed sections; renderedHeaders maps groupIndex -> node.
        let currentPhotoGroup = 'none';
        let gridGroups = null;
        let collapsedGroups = new Set();
        const renderedHeaders = new Map();
        const GROUP_HEADER_H = 40;
        let lightboxCurrentIndex = 0;
        let transferContext = null;
        let hideUnnamedPersons = false;
        let selectedPhotos = new Set();
        let lastSelectedIndex = -1;
        let nameConflictData = null;
        let showFaceTagsPreview = true;
        // F4: whether the preview lightbox shows its right-hand details panel. Backed by
        // the persisted 'show_photo_details' setting; a GUI toggle will drive
        // setShowPhotoDetails() later. When off, the image uses the full width.
        let showPhotoDetails = true;

        // People-list multi-select (F9). Mirrors the grid's selectedPhotos pattern:
        // ctrl/cmd toggles, shift selects a range. selectedPeople holds person ids;
        // currentPeopleOrder is the displayed order (for shift-range index math).
        let selectedPeople = new Set();
        let lastSelectedPersonIndex = -1;
        let currentPeopleOrder = [];

        // Virtualized photo-grid state. lightboxPhotos holds the full metadata list
        // for the current person (no thumbnails); only a window of DOM cells is
        // rendered at any moment and thumbnails are loaded on demand.
        let currentGridSize = 180;           // cell min size in px (from settings)
        let gridViewMode = 'entire_photo';   // 'entire_photo' or 'zoom_to_faces'
        const GRID_GAP = 16;                 // px gap between cells (matches CSS)
        const GRID_BUFFER_ROWS = 3;          // extra rows rendered above/below the view
        const THUMB_CACHE_MAX = 400;         // cap on cached thumbnails (bounds memory)
        let gridGeom = { cols: 1, cellW: 180, cellH: 180, rowH: 196, total: 0 };
        let renderedItems = new Map();       // photo index -> DOM node currently shown
        let thumbCache = new Map();          // face_id -> thumbnail data URL (LRU-ish)
        let gridReqSeq = 0;                  // bumped to discard stale async thumb loads
        let gridScrollScheduled = false;     // rAF throttle flag for scroll
        let sharedContextMenu = null;        // single reused photo context-menu element

        const personColors = [
            '#667eea', '#f093fb', '#4facfe', '#43e97b', '#fa709a',
            '#30cfd0', '#a8edea', '#fed6e3', '#c1dfc4', '#d299c2',
            '#fda085', '#f6d365', '#96e6a1', '#764ba2', '#f79d00'
        ];


        function showRenameDialog(clusteringId, personId, currentName) {
            const cleanName = currentName.replace(' (hidden)', '');
            
            renameContext = {
                clusteringId: clusteringId,
                personId: personId
            };
            
            const renameOverlay = document.getElementById('renameOverlay');
            const renameInput = document.getElementById('renameInput');
            
            renameInput.value = cleanName;
            renameOverlay.classList.add('active');
            appContainer.classList.add('blurred');
            
            setTimeout(() => {
                renameInput.focus();
                renameInput.select();
            }, 100);
        }

        function closeRenameDialog() {
            const renameOverlay = document.getElementById('renameOverlay');
            renameOverlay.classList.remove('active');
            appContainer.classList.remove('blurred');
            renameContext = null;
            document.getElementById('renameInput').value = '';
        }

        function showNameConflictDialog(conflictInfo, originalName) {
            console.log('Showing conflict dialog with:', conflictInfo);
            console.log('Original name attempted:', originalName);
            
            nameConflictData = {
                clusteringId: renameContext.clusteringId,
                personId: renameContext.personId,
                originalName: originalName,
                suggestedName: conflictInfo.suggested_name
            };
            
            console.log('nameConflictData set to:', nameConflictData);
            
            document.getElementById('autoRenameText').textContent = `Name them "${conflictInfo.suggested_name}"`;
            
            const conflictOverlay = document.getElementById('nameConflictOverlay');
            conflictOverlay.classList.add('active');
        }

        function closeNameConflictDialog() {
            const conflictOverlay = document.getElementById('nameConflictOverlay');
            conflictOverlay.classList.remove('active');
            nameConflictData = null;
        }
        
        function getPersonColor(personId) {
            return personColors[personId % personColors.length];
        }

        function updateSelectionInfo() {
            const selectionInfo = document.getElementById('selectionInfo');
            if (!selectionInfo) {
                const info = document.createElement('div');
                info.className = 'selection-info';
                info.id = 'selectionInfo';
                info.innerHTML = `
                    <div class="selection-info-text">
                        <span id="selectionCount">0</span> photos selected
                        <button class="clear-selection-btn" onclick="clearSelection()">Clear</button>
                    </div>
                `;
                document.body.appendChild(info);
            }
            
            const count = selectedPhotos.size;
            if (count > 0) {
                document.getElementById('selectionInfo').classList.add('show');
                document.getElementById('selectionCount').textContent = count;
            } else {
                document.getElementById('selectionInfo').classList.remove('show');
            }
        }

        function clearSelection() {
            selectedPhotos.clear();
            lastSelectedIndex = -1;
            document.querySelectorAll('.photo-item.selected').forEach(item => {
                item.classList.remove('selected');
            });
            updateSelectionInfo();
        }

        function togglePhotoSelection(faceId, photoIndex, element) {
            if (selectedPhotos.has(faceId)) {
                selectedPhotos.delete(faceId);
                element.classList.remove('selected');
            } else {
                selectedPhotos.add(faceId);
                element.classList.add('selected');
                lastSelectedIndex = photoIndex;
            }
            updateSelectionInfo();
        }

        function selectPhotoRange(startIndex, endIndex) {
            // Select every photo between two indices in the full metadata list.
            // Indices address lightboxPhotos (all faces), not DOM nodes, because
            // with virtualization most cells in the range are not rendered.
            // Selection lives in the selectedPhotos set; any cell currently on
            // screen also gets the 'selected' class, and off-screen cells pick it
            // up from the set when they scroll into view (see createPhotoItem).
            const start = Math.min(startIndex, endIndex);
            const end = Math.max(startIndex, endIndex);

            for (let i = start; i <= end && i < lightboxPhotos.length; i++) {
                const faceId = lightboxPhotos[i].face_id;
                selectedPhotos.add(faceId);
                const node = renderedItems.get(i);
                if (node) node.classList.add('selected');
            }
            lastSelectedIndex = endIndex;
            updateSelectionInfo();
        }

        function positionMenu(menu, button) {
            const buttonRect = button.getBoundingClientRect();
            const menuRect = menu.getBoundingClientRect();
            const viewportHeight = window.innerHeight;
            const viewportWidth = window.innerWidth;

            let top = buttonRect.bottom + 4;
            let left = buttonRect.right - menuRect.width;

            if (top + menuRect.height > viewportHeight) {
                top = buttonRect.top - menuRect.height - 4;
            }

            if (left < 0) {
                left = buttonRect.left;
            }

            if (left + menuRect.width > viewportWidth) {
                left = viewportWidth - menuRect.width - 8;
            }

            menu.style.top = top + 'px';
            menu.style.left = left + 'px';
        }

        // Position a menu at a point (used for right-click), clamped to the viewport.
        // The menu must already be visible so its size can be measured.
        function positionMenuAt(menu, x, y) {
            const menuRect = menu.getBoundingClientRect();
            const viewportWidth = window.innerWidth;
            const viewportHeight = window.innerHeight;

            let left = x;
            let top = y;

            if (left + menuRect.width > viewportWidth) left = viewportWidth - menuRect.width - 8;
            if (top + menuRect.height > viewportHeight) top = viewportHeight - menuRect.height - 8;
            if (left < 0) left = 8;
            if (top < 0) top = 8;

            menu.style.left = left + 'px';
            menu.style.top = top + 'px';
        }

        function sortPeople(peopleArray, mode) {
            const sorted = [...peopleArray];
            
            switch(mode) {
                case 'names_asc':
                    sorted.sort((a, b) => a.name.localeCompare(b.name));
                    break;
                case 'names_desc':
                    sorted.sort((a, b) => b.name.localeCompare(a.name));
                    break;
                case 'photos_asc':
                    sorted.sort((a, b) => a.count - b.count);
                    break;
                case 'photos_desc':
                    sorted.sort((a, b) => b.count - a.count);
                    break;
            }

            // Pinned people float to the top regardless of sort mode (F9). filter()
            // is stable, so multiple pinned keep their order among themselves from
            // the sort above, sitting above all unpinned people.
            const pinned = sorted.filter(p => p.is_pinned);
            const unpinned = sorted.filter(p => !p.is_pinned);
            return [...pinned, ...unpinned];
        }

        function getAvailableAlphabets(peopleArray) {
            const alphabets = new Set();
            peopleArray.forEach(person => {
                const firstChar = person.name.charAt(0).toUpperCase();
                if (firstChar.match(/[A-Z]/)) {
                    alphabets.add(firstChar);
                }
            });
            return Array.from(alphabets).sort();
        }

        function scrollToAlphabet(letter) {
            const peopleList = document.getElementById('peopleList');
            const items = peopleList.querySelectorAll('.person-item');
            
            for (let item of items) {
                const nameEl = item.querySelector('.person-name');
                if (nameEl && nameEl.textContent.charAt(0).toUpperCase() === letter) {
                    item.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    break;
                }
            }
        }

        function renderAlphabetList() {
            const peopleList = document.getElementById('peopleList');
            peopleList.innerHTML = '';
            
            const filteredPeople = people.filter(person => {
                if (person.id === 0 && !showUnmatched) {
                    return false;
                }
                if (minPhotosEnabled && person.count < minPhotosCount) {
                    return false;
                }
                return true;
            });
            
            const sortedPeople = sortPeople(filteredPeople, currentSortMode);
            const availableLetters = getAvailableAlphabets(sortedPeople);
            const allLetters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
            
            if (currentSortMode === 'names_desc') {
                allLetters.reverse();
            }
            
            allLetters.forEach(letter => {
                const item = document.createElement('div');
                item.className = 'alphabet-item';
                item.textContent = letter;
                
                if (availableLetters.includes(letter)) {
                    item.addEventListener('click', () => {
                        isAlphabetMode = false;
                        renderPeopleList();
                        setTimeout(() => scrollToAlphabet(letter), 100);
                    });
                } else {
                    item.classList.add('disabled');
                }
                
                peopleList.appendChild(item);
            });
        }

        async function updateCacheSize() {
            try {
                const stats = await pywebview.api.get_cache_stats();
                const sizeText = stats.file_count > 0 
                    ? `${stats.size_mb} MB (${stats.file_count} files)`
                    : 'Cache empty';
                document.getElementById('cacheSize').textContent = sizeText;
            } catch (error) {
                document.getElementById('cacheSize').textContent = 'Unable to calculate';
            }
        }

        async function clearThumbnailCache() {
            const confirmClear = confirm('Clear all cached thumbnails? This will free up disk space but photos will need to be regenerated on next view.');
            
            if (confirmClear) {
                const clearBtn = document.getElementById('clearCacheBtn');
                clearBtn.disabled = true;
                clearBtn.textContent = 'Clearing...';
                
                try {
                    const stats = await pywebview.api.clear_thumbnail_cache();
                    addLogEntry(`Thumbnail cache cleared: ${stats.size_mb} MB freed (${stats.file_count} files removed)`);
                    
                    document.getElementById('cacheSize').textContent = 'Cache empty';
                    
                    alert(`Successfully cleared ${stats.size_mb} MB of cached thumbnails!`);
                    
                } catch (error) {
                    addLogEntry(`Error clearing cache: ${error}`);
                    alert('Error clearing cache. Please try again.');
                } finally {
                    clearBtn.disabled = false;
                    clearBtn.textContent = 'Clear Cache';
                }
            }
        }

        async function loadPeople() {
            try {
                people = await pywebview.api.get_people();
                renderPeopleList();
                
                if (people.length > 0) {
                    const firstPerson = people.find(p => p.id !== 0) || people[0];
                    selectPerson(firstPerson);
                }
            } catch (error) {
                console.error('Error loading people:', error);
            }
        }

        function renderPeopleList() {
            const peopleList = document.getElementById('peopleList');
            peopleList.innerHTML = '';
            
            const filteredPeople = people.filter(person => {
                if (person.id === 0 && !showUnmatched) {
                    return false;
                }
                if (minPhotosEnabled && person.count < minPhotosCount) {
                    return false;
                }
                return true;
            });
            
            const sortedPeople = sortPeople(filteredPeople, currentSortMode);
            currentPeopleOrder = sortedPeople;

            sortedPeople.forEach(person => {
                const item = document.createElement('div');
                item.className = 'person-item';
                item.dataset.personId = person.id;
                if (currentPerson && person.id === currentPerson.id) {
                    item.classList.add('active');
                }
                if (selectedPeople.has(person.id)) {
                    item.classList.add('selected');
                }

                const color = getPersonColor(person.id);
                const initial = person.name.charAt(0);

                const tagInfo = (showDevOptions && person.tagged_count > 0) ? ` (${person.tagged_count}/${person.count} tagged)` : '';

                let avatarHTML;
                if (person.thumbnail) {
                    avatarHTML = `<img src="${person.thumbnail}" class="person-avatar" style="width: 44px; height: 44px; object-fit: cover;">`;
                } else {
                    avatarHTML = `<div class="person-avatar" style="background: linear-gradient(135deg, ${color} 0%, ${color}99 100%)">${initial}</div>`;
                }

                // Pin indicator on the right edge, only when pinned (F9).
                const pinHTML = person.is_pinned ? `<span class="person-pin">${SVG_PINNED}</span>` : '';

                item.innerHTML = `
                    ${avatarHTML}
                    <div class="person-info">
                        <div class="person-name">${person.name}</div>
                        <div class="person-count">${person.count} photos${tagInfo}</div>
                    </div>
                    ${pinHTML}
                    <button class="kebab-menu">
                        <span class="kebab-dot"></span>
                        <span class="kebab-dot"></span>
                        <span class="kebab-dot"></span>
                    </button>
                `;

                // The menu is populated at open time (buildPersonMenuHTML) so it
                // reflects the live multi-selection: 2+ selected shows the group menu,
                // otherwise the per-person menu.
                const contextMenu = document.createElement('div');
                contextMenu.className = 'context-menu';
                document.body.appendChild(contextMenu);

                item.addEventListener('click', (e) => {
                    if (e.target.closest('.kebab-menu') || e.target.closest('.context-menu')) return;
                    handlePersonClick(e, person);
                });

                peopleList.appendChild(item);

                const kebabBtn = item.querySelector('.kebab-menu');
                kebabBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    openPersonMenu(person, item, contextMenu, () => positionMenu(contextMenu, kebabBtn));
                });

                // Right-click anywhere on the person row opens the same menu at the cursor.
                item.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    openPersonMenu(person, item, contextMenu, () => positionMenuAt(contextMenu, e.clientX, e.clientY));
                });
            });
        }

        // People-list click dispatch (F9). Mirrors the grid: ctrl/cmd toggles a row,
        // shift extends a range, a plain click drops any multi-selection and navigates
        // to that person.
        function handlePersonClick(e, person) {
            const index = currentPeopleOrder.findIndex(p => p.id === person.id);
            if (e.ctrlKey || e.metaKey) {
                togglePersonSelection(person.id, index);
            } else if (e.shiftKey) {
                if (lastSelectedPersonIndex >= 0) {
                    selectPersonRange(lastSelectedPersonIndex, index);
                } else {
                    selectedPeople.add(person.id);
                    lastSelectedPersonIndex = index;
                    applyPeopleSelectionClasses();
                    updatePeopleSelectionInfo();
                }
            } else {
                clearPeopleSelection();
                selectPerson(person);
            }
        }

        function togglePersonSelection(personId, index) {
            if (selectedPeople.has(personId)) {
                selectedPeople.delete(personId);
            } else {
                selectedPeople.add(personId);
                lastSelectedPersonIndex = index;
            }
            applyPeopleSelectionClasses();
            updatePeopleSelectionInfo();
        }

        function selectPersonRange(startIndex, endIndex) {
            const lo = Math.min(startIndex, endIndex);
            const hi = Math.max(startIndex, endIndex);
            for (let i = lo; i <= hi && i < currentPeopleOrder.length; i++) {
                selectedPeople.add(currentPeopleOrder[i].id);
            }
            lastSelectedPersonIndex = endIndex;
            applyPeopleSelectionClasses();
            updatePeopleSelectionInfo();
        }

        // Sync the 'selected' class on currently rendered rows from the selectedPeople set.
        function applyPeopleSelectionClasses() {
            document.querySelectorAll('.person-item').forEach(item => {
                const pid = parseInt(item.dataset.personId, 10);
                item.classList.toggle('selected', selectedPeople.has(pid));
            });
        }

        function clearPeopleSelection() {
            selectedPeople.clear();
            lastSelectedPersonIndex = -1;
            document.querySelectorAll('.person-item.selected').forEach(i => i.classList.remove('selected'));
            updatePeopleSelectionInfo();
        }

        // Floating count bar for the people selection. Same look as the grid bar but
        // left-aligned (see .people-selection-info) so it reads as belonging to the
        // people list.
        function updatePeopleSelectionInfo() {
            let bar = document.getElementById('peopleSelectionInfo');
            if (!bar) {
                bar = document.createElement('div');
                bar.className = 'selection-info people-selection-info';
                bar.id = 'peopleSelectionInfo';
                document.body.appendChild(bar);
            }
            const count = selectedPeople.size;
            if (count > 0) {
                const noun = count === 1 ? 'person' : 'people';
                bar.innerHTML = `<div class="selection-info-text">${count} ${noun} selected<button class="clear-selection-btn" onclick="clearPeopleSelection()">Clear</button></div>`;
                bar.classList.add('show');
            } else {
                bar.classList.remove('show');
            }
        }

        // Open a person's context menu. Mirrors the grid: if a selection is active and
        // this row isn't part of it, the row is added first, so the menu acts on the
        // group the user is pointing at. buildPersonMenuHTML then decides single vs group.
        function openPersonMenu(person, item, contextMenu, anchorFn) {
            closeAllMenus();
            if (selectedPeople.size > 0 && !selectedPeople.has(person.id)) {
                const idx = currentPeopleOrder.findIndex(p => p.id === person.id);
                selectedPeople.add(person.id);
                lastSelectedPersonIndex = idx;
                applyPeopleSelectionClasses();
                updatePeopleSelectionInfo();
            }
            contextMenu.innerHTML = buildPersonMenuHTML(person);
            contextMenu.classList.add('show');
            item.classList.add('menu-active');
            activeMenu = { element: contextMenu, parent: item };
            anchorFn();
        }

        // Build the menu HTML for a person row at open time. 2+ selected (and this row
        // among them) yields the group menu: Export Selected, plus Pin/Unpin only when
        // the whole selection is uniformly unpinned/pinned (mixed shows neither).
        function buildPersonMenuHTML(person) {
            const multi = selectedPeople.size >= 2 && selectedPeople.has(person.id);
            if (multi) {
                let html = `<div class="context-menu-item" onclick="exportSelectedPeople()">Export Selected to Folder</div>`;
                const sel = people.filter(p => selectedPeople.has(p.id));
                // Pin/Unpin and Hide/Unhide each appear only when the whole selection
                // is uniform; a mixed selection shows neither (same rule for both).
                if (sel.every(p => !p.is_pinned)) {
                    html += `<div class="context-menu-item" onclick="pinSelectedPeople()">Pin</div>`;
                } else if (sel.every(p => p.is_pinned)) {
                    html += `<div class="context-menu-item" onclick="unpinSelectedPeople()">Unpin</div>`;
                }
                if (sel.every(p => !p.is_hidden)) {
                    html += `<div class="context-menu-item" onclick="hideSelectedPeople()">Hide</div>`;
                } else if (sel.every(p => p.is_hidden)) {
                    html += `<div class="context-menu-item" onclick="unhideSelectedPeople()">Unhide</div>`;
                }
                return html;
            }

            const cleanPersonName = person.name.replace(' (hidden)', '');
            const escapedName = cleanPersonName.replace(/'/g, "\\'");
            // "Unmatched Faces" is a grab-bag, not a real person, so it is not exportable.
            const exportItem = cleanPersonName !== 'Unmatched Faces'
                ? `<div class="context-menu-item" onclick="exportPerson(${person.clustering_id}, ${person.id}, '${escapedName}')">Export photos...</div>`
                : '';
            const pinItem = person.is_pinned
                ? `<div class="context-menu-item" onclick="unpinPerson(${person.clustering_id}, ${person.id})">Unpin</div>`
                : `<div class="context-menu-item" onclick="pinPerson(${person.clustering_id}, ${person.id})">Pin</div>`;

            let menuHTML = `<div class="context-menu-item" onclick="renamePerson(${person.clustering_id}, ${person.id}, '${escapedName}')">Rename</div>`;
            if (showDevOptions) {
                menuHTML += `<div class="context-menu-item" onclick="untagPerson(${person.clustering_id}, ${person.id})">Remove all tags</div>`;
            }
            menuHTML += exportItem;
            menuHTML += pinItem;
            menuHTML += person.is_hidden
                ? `<div class="context-menu-item" onclick="unhidePerson(${person.clustering_id}, ${person.id})">Unhide person</div>`
                : `<div class="context-menu-item" onclick="hidePerson(${person.clustering_id}, ${person.id})">Hide person</div>`;
            return menuHTML;
        }

        // Re-fetch people (for the fresh is_pinned flags) and re-render without changing
        // the current selection or the navigated person. Used after pin/unpin.
        async function refreshPeople() {
            people = await pywebview.api.get_people();
            renderPeopleList();
            updatePeopleSelectionInfo();
        }

        async function pinPerson(clusteringId, personId) {
            closeAllMenus();
            await pywebview.api.pin_person(clusteringId, personId);
            await refreshPeople();
        }

        async function unpinPerson(clusteringId, personId) {
            closeAllMenus();
            await pywebview.api.unpin_person(clusteringId, personId);
            await refreshPeople();
        }

        async function pinSelectedPeople() {
            closeAllMenus();
            const sel = people.filter(p => selectedPeople.has(p.id));
            for (const p of sel) {
                await pywebview.api.pin_person(p.clustering_id, p.id);
            }
            await refreshPeople();
        }

        async function unpinSelectedPeople() {
            closeAllMenus();
            const sel = people.filter(p => selectedPeople.has(p.id));
            for (const p of sel) {
                await pywebview.api.unpin_person(p.clustering_id, p.id);
            }
            await refreshPeople();
        }

        // Hide/unhide the whole selection at once (F9). Unlike pin, the affected rows
        // can leave the list (when show-hidden is off), so the selection is cleared
        // afterwards rather than kept.
        async function hideSelectedPeople() {
            closeAllMenus();
            const sel = people.filter(p => selectedPeople.has(p.id));
            if (sel.length === 0) return;
            await pywebview.api.hide_persons(sel[0].clustering_id, sel.map(p => p.id));
            clearPeopleSelection();
            await refreshPeople();
        }

        async function unhideSelectedPeople() {
            closeAllMenus();
            const sel = people.filter(p => selectedPeople.has(p.id));
            if (sel.length === 0) return;
            await pywebview.api.unhide_persons(sel[0].clustering_id, sel.map(p => p.id));
            clearPeopleSelection();
            await refreshPeople();
        }

        async function exportSelectedPeople() {
            closeAllMenus();
            const ids = Array.from(selectedPeople);
            if (ids.length === 0) return;
            const dest = await pywebview.api.select_folder();
            if (!dest) return;
            const mode = getExportMode();
            const label = `Exporting ${ids.length} ${ids.length === 1 ? 'person' : 'people'}`;
            await beginExport(label, dest, () => pywebview.api.export_selected(ids, dest, mode));
        }

        async function selectPerson(person) {
            currentPerson = person;
            clearSelection();
            
            document.getElementById('contentTitle').textContent = `${person.name}'s Photos`;
            
            document.querySelectorAll('.person-item').forEach(item => {
                item.classList.remove('active');
            });
            
            const items = document.querySelectorAll('.person-item');
            items.forEach(item => {
                const nameEl = item.querySelector('.person-name');
                if (nameEl && nameEl.textContent === person.name) {
                    item.classList.add('active');
                }
            });
            
            await loadPersonPhotos(person.clustering_id, person.id);
        }


        /**
         * Load all photos for a person and render the virtualized grid.
         *
         * Fetches only lightweight metadata (no thumbnails) for the whole person,
         * stores it in lightboxPhotos, then renders just the cells that fit in the
         * viewport; thumbnails for visible cells are fetched on demand by loadThumb.
         * This replaces the old approach of appending every page into the DOM with
         * an inline base64 thumbnail, which accumulated thousands of nodes and
         * hundreds of MB of decoded images and eventually froze the app.
         */
        async function loadPersonPhotos(clustering_id, person_id) {
            const photoGrid = document.getElementById('photoGrid');

            // Reset all grid state for the new person.
            clearSelection();
            lightboxPhotos = [];
            renderedItems.clear();
            renderedHeaders.clear();
            collapsedGroups.clear();   // collapse state is per-person
            thumbCache.clear();
            photoGrid.style.height = '';
            photoGrid.innerHTML = '<div style="color: #a0a0a0; padding: 20px;">Loading photos...</div>';

            // Tag this request so async thumbnail loads from a previous person can be
            // discarded if the user switches people before they resolve.
            const mySeq = ++gridReqSeq;

            try {
                const result = await pywebview.api.get_person_photo_list(clustering_id, person_id);
                if (mySeq !== gridReqSeq) return;   // a newer load superseded this one

                allPersonPhotos = (result && Array.isArray(result.photos)) ? result.photos : [];
                // Filter is per-person (extensions differ between people); reset it on
                // every load. The sort preference persists across people.
                photoFilter = { exts: null, pathText: '' };
                buildSortOptions();

                if (allPersonPhotos.length === 0) {
                    lightboxPhotos = [];
                    gridGroups = null;       // no stale grouped layout
                    computeGridGeometry();   // reset gridGeom.total to 0 (no stale layout)
                    photoGrid.innerHTML = '<div style="color: #a0a0a0; padding: 20px;">No photos found</div>';
                    updatePhotoCountTitle();
                    updateFilterButtonLabel();
                    updateGroupButtonLabel();
                    return;
                }

                photoGrid.innerHTML = '';
                applyPhotoView();
            } catch (error) {
                console.error('Error loading photos:', error);
                addLogEntry('ERROR loading photos: ' + error.toString());
                photoGrid.innerHTML = `<div style="color: #ff6b6b; padding: 20px;">Error loading photos: ${error.toString()}</div>`;
            }
        }

        // ---- F2: per-person photo sort + filter -------------------------------------
        // A facet (date/size/device) is only offered as a sort option when at least this
        // fraction of the person's photos have a value for it (the "50% rule"). Name,
        // path and extension are derived from the filename, so they're always available.
        const FACET_THRESHOLD = 0.5;

        // Sort options grouped into categories (rendered as <optgroup>s). cat=null is the
        // ungrouped default at the top. facet = the metadata field that must clear the
        // 50% threshold for the option to appear (null = always available, path-derived).
        const PHOTO_SORT_OPTIONS = [
            { value: 'default',       label: 'Default Sort Order',         cat: null,    facet: null },
            { value: 'name_asc',      label: 'File name (A-Z)',            cat: 'Names',  facet: null },
            { value: 'name_desc',     label: 'File name (Z-A)',            cat: 'Names',  facet: null },
            { value: 'pathname_asc',  label: 'File path + name (A-Z)',     cat: 'Names',  facet: null },
            { value: 'pathname_desc', label: 'File path + name (Z-A)',     cat: 'Names',  facet: null },
            { value: 'taken_desc',    label: 'Date taken (newest)',        cat: 'Dates',  facet: 'date_taken' },
            { value: 'taken_asc',     label: 'Date taken (oldest)',        cat: 'Dates',  facet: 'date_taken' },
            { value: 'modified_desc', label: 'Date modified (newest)',     cat: 'Dates',  facet: 'date_modified' },
            { value: 'modified_asc',  label: 'Date modified (oldest)',     cat: 'Dates',  facet: 'date_modified' },
            { value: 'created_desc',  label: 'Date created (newest)',      cat: 'Dates',  facet: 'date_created' },
            { value: 'created_asc',   label: 'Date created (oldest)',      cat: 'Dates',  facet: 'date_created' },
            { value: 'size_desc',     label: 'Larger first',               cat: 'Size',   facet: 'file_size' },
            { value: 'size_asc',      label: 'Smaller first',              cat: 'Size',   facet: 'file_size' },
        ];
        const PHOTO_SORT_CATEGORIES = ['Names', 'Dates', 'Size'];

        // mode -> [keyName, direction]
        const PHOTO_SORT_DEFS = {
            name_asc: ['name', 'asc'], name_desc: ['name', 'desc'],
            pathname_asc: ['path', 'asc'], pathname_desc: ['path', 'desc'],
            taken_desc: ['date_taken', 'desc'], taken_asc: ['date_taken', 'asc'],
            modified_desc: ['date_modified', 'desc'], modified_asc: ['date_modified', 'asc'],
            created_desc: ['date_created', 'desc'], created_asc: ['date_created', 'asc'],
            size_desc: ['file_size', 'desc'], size_asc: ['file_size', 'asc'],
        };

        function photoExt(p) {
            if (p.meta && p.meta.file_ext) return p.meta.file_ext;
            const name = p.name || '';
            const dot = name.lastIndexOf('.');
            return dot >= 0 ? name.slice(dot + 1).toLowerCase() : '';
        }

        // Parent folder of a photo (derived from its path, so always available).
        function photoDir(p) {
            const path = p.path || '';
            const i = Math.max(path.lastIndexOf('\\'), path.lastIndexOf('/'));
            return i >= 0 ? path.slice(0, i) : '';
        }

        // ---- Grouping options + key/label -------------------------------------------
        // Clickable group modes, grouped into categories (rendered in the Group panel).
        // facet = the metadata field that must clear the 50% threshold for the mode to be
        // offered (null = always available, path-derived).
        const PHOTO_GROUP_OPTIONS = [
            { value: 'folder',         label: 'File path',         cat: 'Folders',       facet: null },
            { value: 'date_days',      label: 'Days',              cat: 'Date taken',    facet: 'date_taken' },
            { value: 'date_week',      label: 'Weeks',             cat: 'Date taken',    facet: 'date_taken' },
            { value: 'date_month',     label: 'Months',            cat: 'Date taken',    facet: 'date_taken' },
            { value: 'date_year',      label: 'Years',             cat: 'Date taken',    facet: 'date_taken' },
            { value: 'modified_days',  label: 'Days',              cat: 'Date modified', facet: 'date_modified' },
            { value: 'modified_week',  label: 'Weeks',             cat: 'Date modified', facet: 'date_modified' },
            { value: 'modified_month', label: 'Months',            cat: 'Date modified', facet: 'date_modified' },
            { value: 'modified_year',  label: 'Years',             cat: 'Date modified', facet: 'date_modified' },
            { value: 'created_days',   label: 'Days',              cat: 'Date created',  facet: 'date_created' },
            { value: 'created_week',   label: 'Weeks',             cat: 'Date created',  facet: 'date_created' },
            { value: 'created_month',  label: 'Months',            cat: 'Date created',  facet: 'date_created' },
            { value: 'created_year',   label: 'Years',             cat: 'Date created',  facet: 'date_created' },
            { value: 'device',         label: 'Camera make/model', cat: 'Others',        facet: 'device' },
        ];
        const PHOTO_GROUP_CATEGORIES = ['Folders', 'Date taken', 'Date modified', 'Date created', 'Others'];

        // Date grouping modes -> which metadata field to bucket and the granularity.
        const DATE_GROUP_MODES = {
            date_days: { field: 'date_taken', bucket: 'days' },
            date_week: { field: 'date_taken', bucket: 'week' },
            date_month: { field: 'date_taken', bucket: 'month' },
            date_year: { field: 'date_taken', bucket: 'year' },
            modified_days: { field: 'date_modified', bucket: 'days' },
            modified_week: { field: 'date_modified', bucket: 'week' },
            modified_month: { field: 'date_modified', bucket: 'month' },
            modified_year: { field: 'date_modified', bucket: 'year' },
            created_days: { field: 'date_created', bucket: 'days' },
            created_week: { field: 'date_created', bucket: 'week' },
            created_month: { field: 'date_created', bucket: 'month' },
            created_year: { field: 'date_created', bucket: 'year' },
        };

        // Inlined group-header icons (from app/svg/{expand,collapse}-group.svg) so they
        // render without depending on the static file server. The icon shows the ACTION a
        // click performs: a collapsed group shows expand-group; an expanded group shows
        // collapse-group.
        const SVG_EXPAND = '<svg viewBox="-230.4 -230.4 2380.80 2380.80" width="13" height="13" fill="#cfcfcf" stroke="#cfcfcf" stroke-width="59.52"><path d="M959.921.01 453 506.933l152.28 152.28 246.946-246.944v1095.475L605.28 1260.798 453 1413.078 959.921 1920l506.921-506.921-152.28-152.281-246.946 246.945V412.268l246.945 246.945 152.281-152.281z" fill-rule="evenodd"/></svg>';
        const SVG_COLLAPSE = '<svg viewBox="0 0 16 16" width="13" height="13" fill="#cfcfcf"><path d="M4.414,15.414L8,11.828L11.586,15.414L13,14L8,9L3,14L4.414,15.414ZM11.586,0.586L8,4.172L4.414,0.586L3,2L8,7L13,2L11.586,0.586Z"/></svg>';

        // Inlined pin icon (from app/svg/pinned.svg) shown on the right edge of a
        // pinned person row (F9).
        const SVG_PINNED = '<svg viewBox="0 0 56 56" width="12" height="12" fill="#cfcfcf"><path d="M 14.2539 35.9688 L 25.9492 35.9688 L 25.9492 48.0156 C 25.9492 51.5781 27.4258 54.5781 28.0117 54.5781 C 28.5976 54.5781 30.0742 51.5781 30.0742 48.0156 L 30.0742 35.9688 L 41.7461 35.9688 C 43.3633 35.9688 44.5351 34.9375 44.5351 33.3672 C 44.5351 32.3828 44.2305 31.6797 43.5508 30.9532 L 36.3789 23.1719 C 35.8867 22.6563 35.5820 22.2813 35.6992 21.3203 L 36.8945 12.7657 C 36.9649 12.2735 37.0117 11.9922 37.4336 11.6875 L 43.1992 7.5157 C 44.4883 6.5781 45.0508 5.4297 45.0508 4.3750 C 45.0508 2.8047 43.7851 1.4219 41.9805 1.4219 L 14.0195 1.4219 C 12.2149 1.4219 10.9492 2.8047 10.9492 4.3750 C 10.9492 5.4297 11.5117 6.5781 12.7773 7.5157 L 18.5429 11.6875 C 18.9883 11.9922 19.0351 12.2735 19.1054 12.7657 L 20.3008 21.3203 C 20.4180 22.2813 20.1133 22.6563 19.6211 23.1719 L 12.4492 30.9532 C 11.7695 31.6797 11.4649 32.3828 11.4649 33.3672 C 11.4649 34.9375 12.6367 35.9688 14.2539 35.9688 Z"/></svg>';

        function pad2(n) { return n < 10 ? '0' + n : '' + n; }

        // ISO-8601 week number (Mon-based) and its week-year.
        function isoWeek(d) {
            const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
            const day = (date.getUTCDay() + 6) % 7;     // Mon=0..Sun=6
            date.setUTCDate(date.getUTCDate() - day + 3); // nearest Thursday
            const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4));
            const week = 1 + Math.round(
                ((date - firstThursday) / 86400000 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7);
            return { year: date.getUTCFullYear(), week };
        }

        // {key, label, sortKey} for a photo under a grouping mode. key===null => the
        // photo has no value for this facet (goes to the "No Data Available" group).
        function groupKeyLabel(p, mode) {
            const m = p.meta || {};
            if (mode === 'folder') {
                const d = photoDir(p);
                return d ? { key: d, label: d, sortKey: 0 } : { key: null };
            }
            if (mode === 'device') {
                const dev = ((m.camera_make || '') + ' ' + (m.camera_model || '')).trim();
                return dev ? { key: dev.toLowerCase(), label: dev, sortKey: 0 } : { key: null };
            }
            const dm = DATE_GROUP_MODES[mode];
            if (dm) {
                const ts = m[dm.field];
                if (ts === null || ts === undefined) return { key: null };
                const d = new Date(ts * 1000);
                if (dm.bucket === 'days') {
                    return {
                        key: `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`,
                        label: d.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }),
                        sortKey: ts,
                    };
                }
                if (dm.bucket === 'month') {
                    return {
                        key: `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`,
                        label: d.toLocaleDateString(undefined, { year: 'numeric', month: 'long' }),
                        sortKey: d.getFullYear() * 12 + d.getMonth(),
                    };
                }
                if (dm.bucket === 'year') {
                    return { key: String(d.getFullYear()), label: String(d.getFullYear()), sortKey: d.getFullYear() };
                }
                if (dm.bucket === 'week') {
                    const w = isoWeek(d);
                    return { key: `${w.year}-W${pad2(w.week)}`, label: `Week ${w.week}, ${w.year}`, sortKey: w.year * 53 + w.week };
                }
            }
            return { key: null };
        }

        // Partition an already-sorted list into ordered group descriptors and return the
        // flattened photo list (group order, within-group sort preserved). Date groups are
        // ordered newest-first; folder/device alphabetically; "No Data Available" last.
        function buildGroups(sorted, mode) {
            const map = new Map();
            let noData = null;
            for (const p of sorted) {
                const kl = groupKeyLabel(p, mode);
                if (kl.key === null) {
                    if (!noData) noData = { key: '__nodata__', label: 'No Data Available', sortKey: -Infinity, photos: [] };
                    noData.photos.push(p);
                    continue;
                }
                let g = map.get(kl.key);
                if (!g) { g = { key: kl.key, label: kl.label, sortKey: kl.sortKey, photos: [] }; map.set(kl.key, g); }
                g.photos.push(p);
            }

            const groups = Array.from(map.values());
            const dateMode = !!DATE_GROUP_MODES[mode];
            groups.sort((a, b) => {
                if (dateMode) return b.sortKey - a.sortKey;           // newest first
                const la = a.label.toLowerCase(), lb = b.label.toLowerCase();
                return la < lb ? -1 : (la > lb ? 1 : 0);              // alphabetical
            });
            if (noData) groups.push(noData);                          // always last

            const flat = [];
            const descriptors = [];
            for (const g of groups) {
                descriptors.push({
                    key: g.key, label: g.label,
                    startIndex: flat.length, count: g.photos.length,
                    collapsed: collapsedGroups.has(g.key),
                });
                for (const p of g.photos) flat.push(p);
            }
            return { flat, groups: descriptors };
        }

        // Is a grouping mode usable for the current person (facet clears the threshold)?
        function groupModeAvailable(mode) {
            if (mode === 'none') return true;
            const opt = PHOTO_GROUP_OPTIONS.find(o => o.value === mode);
            if (!opt) return false;
            return !opt.facet || facetFraction(allPersonPhotos, opt.facet) >= FACET_THRESHOLD;
        }

        function photoSortKey(p, field) {
            const m = p.meta || {};
            switch (field) {
                case 'name': return (p.name || '').toLowerCase();
                case 'path': return (p.path || '').toLowerCase();
                case 'date_taken': return m.date_taken;
                case 'date_modified': return m.date_modified;
                case 'date_created': return m.date_created;
                case 'file_size': return m.file_size;
                case 'device': {
                    const d = ((m.camera_make || '') + ' ' + (m.camera_model || '')).trim().toLowerCase();
                    return d || null;
                }
                default: return null;
            }
        }

        function facetFraction(photos, field) {
            if (photos.length === 0) return 0;
            let have = 0;
            for (const p of photos) {
                const k = photoSortKey(p, field);
                if (k !== null && k !== undefined && k !== '') have++;
            }
            return have / photos.length;
        }

        function buildSortOptions() {
            const dropdown = document.getElementById('photoSortDropdown');
            if (!dropdown) return;
            dropdown.innerHTML = '';
            let sawCurrent = false;

            const available = PHOTO_SORT_OPTIONS.filter(opt =>
                !opt.facet || facetFraction(allPersonPhotos, opt.facet) >= FACET_THRESHOLD);

            const addOption = (parent, opt) => {
                const o = document.createElement('option');
                o.value = opt.value;
                o.textContent = opt.label;
                parent.appendChild(o);
                if (opt.value === currentPhotoSort) sawCurrent = true;
            };

            // Ungrouped (Default) first, then a labelled <optgroup> per non-empty category.
            available.filter(o => o.cat === null).forEach(o => addOption(dropdown, o));
            for (const cat of PHOTO_SORT_CATEGORIES) {
                const opts = available.filter(o => o.cat === cat);
                if (!opts.length) continue;
                const group = document.createElement('optgroup');
                group.label = cat;
                opts.forEach(o => addOption(group, o));
                dropdown.appendChild(group);
            }

            // If the saved sort isn't available for this person, show Default (without
            // overwriting the saved preference).
            dropdown.value = sawCurrent ? currentPhotoSort : 'default';
        }

        function sortPhotos(list, mode) {
            const def = PHOTO_SORT_DEFS[mode];
            if (!def) return list;   // 'default' / unknown -> keep API order
            const [field, dir] = def;
            const factor = dir === 'asc' ? 1 : -1;
            return list.slice().sort((a, b) => {
                const ka = photoSortKey(a, field);
                const kb = photoSortKey(b, field);
                const na = (ka === null || ka === undefined || ka === '');
                const nb = (kb === null || kb === undefined || kb === '');
                if (na && nb) return 0;
                if (na) return 1;    // missing values always sort to the bottom
                if (nb) return -1;
                if (ka < kb) return -1 * factor;
                if (ka > kb) return 1 * factor;
                return 0;
            });
        }

        function filterPhotos(list) {
            let out = list;
            if (photoFilter.exts) {
                out = out.filter(p => photoFilter.exts.has(photoExt(p)));
            }
            if (photoFilter.pathText) {
                out = out.filter(p => (p.path || '').toLowerCase().includes(photoFilter.pathText));
            }
            return out;
        }

        // Recompute the displayed list (lightboxPhotos) from allPersonPhotos and re-render.
        function applyPhotoView() {
            // Use the dropdown's effective value: if the saved sort isn't available for
            // this person, buildSortOptions() shows 'Default', and the order must match.
            const dropdown = document.getElementById('photoSortDropdown');
            const mode = dropdown && dropdown.value ? dropdown.value : currentPhotoSort;
            const sorted = sortPhotos(filterPhotos(allPersonPhotos), mode);

            // Group (if the chosen mode is available for this person). lightboxPhotos is
            // the flattened group order so the grid AND the lightbox follow it.
            const groupMode = groupModeAvailable(currentPhotoGroup) ? currentPhotoGroup : 'none';
            if (groupMode === 'none') {
                lightboxPhotos = sorted;
                gridGroups = null;
            } else {
                const built = buildGroups(sorted, groupMode);
                lightboxPhotos = built.flat;
                gridGroups = built.groups;
            }

            clearSelection();
            renderedItems.clear();
            renderedHeaders.clear();
            const photoGrid = document.getElementById('photoGrid');
            photoGrid.innerHTML = '';
            // Always recompute geometry so gridGeom.total tracks the (possibly empty)
            // list - otherwise a later scroll renders against a stale total.
            computeGridGeometry();
            if (lightboxPhotos.length === 0) {
                photoGrid.innerHTML = '<div style="color: #a0a0a0; padding: 20px;">No photos match the current filter</div>';
            } else {
                renderGridWindow(true);
            }

            updatePhotoCountTitle();
            updateFilterButtonLabel();
            updateGroupButtonLabel();
        }

        function updatePhotoCountTitle() {
            if (!currentPerson) return;
            const shown = lightboxPhotos.length;
            const total = allPersonPhotos.length;
            const suffix = (shown === total) ? ` (${total})` : ` (${shown} of ${total})`;
            document.getElementById('contentTitle').textContent = `${currentPerson.name}'s Photos${suffix}`;
        }

        function updateFilterButtonLabel() {
            const btn = document.getElementById('photoFilterBtn');
            if (!btn) return;
            const active = (photoFilter.exts ? 1 : 0) + (photoFilter.pathText ? 1 : 0);
            btn.textContent = active ? `Filter (${active})` : 'Filter';
            btn.classList.toggle('active', active > 0);
        }

        function buildExtCounts() {
            const counts = {};
            for (const p of allPersonPhotos) {
                const ext = photoExt(p) || '(none)';
                counts[ext] = (counts[ext] || 0) + 1;
            }
            return counts;
        }

        let photoFilterPanel = null;

        function openPhotoFilterPanel() {
            closeAllMenus();
            if (!photoFilterPanel) {
                photoFilterPanel = document.createElement('div');
                photoFilterPanel.className = 'context-menu filter-panel';
                document.body.appendChild(photoFilterPanel);
                // Keep clicks inside the panel from bubbling to the document handler that
                // closes menus.
                photoFilterPanel.addEventListener('click', (e) => e.stopPropagation());
            }

            const counts = buildExtCounts();
            const exts = Object.keys(counts).sort();
            const checked = photoFilter.exts;   // Set or null (null = all)

            let html = '<div class="filter-panel-label">File type</div>';
            if (exts.length === 0) {
                html += '<div class="filter-panel-empty">No photos</div>';
            } else {
                for (const ext of exts) {
                    const isChecked = (checked === null) || checked.has(ext);
                    html += `<label class="filter-check"><input type="checkbox" data-ext="${ext}" ${isChecked ? 'checked' : ''}> ${ext} (${counts[ext]})</label>`;
                }
            }
            html += '<div class="filter-panel-label">Path contains</div>';
            const safePath = photoFilter.pathText.replace(/"/g, '&quot;');
            html += `<input type="text" class="filter-path-input" id="photoPathFilterInput" placeholder="text in file path" value="${safePath}">`;
            html += '<div class="context-menu-item" data-action="clear-filters">Clear filters</div>';
            photoFilterPanel.innerHTML = html;

            photoFilterPanel.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                cb.addEventListener('change', () => {
                    const allExts = Object.keys(buildExtCounts());
                    const checkedExts = Array.from(photoFilterPanel.querySelectorAll('input[type="checkbox"]'))
                        .filter(c => c.checked)
                        .map(c => c.getAttribute('data-ext'));
                    photoFilter.exts = (checkedExts.length === allExts.length) ? null : new Set(checkedExts);
                    applyPhotoView();
                });
            });

            const pathInput = photoFilterPanel.querySelector('#photoPathFilterInput');
            if (pathInput) {
                pathInput.addEventListener('input', () => {
                    photoFilter.pathText = pathInput.value.trim().toLowerCase();
                    applyPhotoView();
                });
            }

            const clearItem = photoFilterPanel.querySelector('[data-action="clear-filters"]');
            if (clearItem) {
                clearItem.addEventListener('click', () => {
                    photoFilter = { exts: null, pathText: '' };
                    applyPhotoView();
                    closeAllMenus();
                });
            }

            photoFilterPanel.classList.add('show');
            activeMenu = { element: photoFilterPanel, parent: document.getElementById('photoFilterBtn') };
            positionMenu(photoFilterPanel, document.getElementById('photoFilterBtn'));
        }

        document.getElementById('photoSortDropdown').addEventListener('change', (e) => {
            currentPhotoSort = e.target.value;
            try { pywebview.api.set_photo_sort_mode(currentPhotoSort); } catch (err) {}
            applyPhotoView();
        });

        document.getElementById('photoFilterBtn').addEventListener('click', (e) => {
            e.stopPropagation();
            if (photoFilterPanel && photoFilterPanel.classList.contains('show')) {
                closeAllMenus();
            } else {
                openPhotoFilterPanel();
            }
        });

        // ---- Group panel (single-select, button + panel like Filter) ----------------
        let photoGroupPanel = null;

        function setPhotoGroup(mode) {
            currentPhotoGroup = mode;
            try { pywebview.api.set_photo_group_mode(mode); } catch (err) {}
            collapsedGroups.clear();   // collapse state is per-grouping
            applyPhotoView();
        }

        function updateGroupButtonLabel() {
            const btn = document.getElementById('photoGroupBtn');
            if (!btn) return;
            const active = gridGroups !== null;
            btn.textContent = active ? 'Grouped' : 'Group';
            btn.classList.toggle('active', active);
        }

        function openPhotoGroupPanel() {
            closeAllMenus();
            if (!photoGroupPanel) {
                photoGroupPanel = document.createElement('div');
                photoGroupPanel.className = 'context-menu filter-panel';
                document.body.appendChild(photoGroupPanel);
                photoGroupPanel.addEventListener('click', (e) => e.stopPropagation());
            }
            photoGroupPanel.innerHTML = '';

            const addItem = (label, value, isActive) => {
                const item = document.createElement('div');
                item.className = 'context-menu-item' + (isActive ? ' active' : '');
                item.textContent = label;
                item.addEventListener('click', () => { setPhotoGroup(value); closeAllMenus(); });
                photoGroupPanel.appendChild(item);
            };
            const addLabel = (text) => {
                const el = document.createElement('div');
                el.className = 'filter-panel-label';
                el.textContent = text;
                photoGroupPanel.appendChild(el);
            };

            addItem('No grouping', 'none', currentPhotoGroup === 'none');
            for (const cat of PHOTO_GROUP_CATEGORIES) {
                const opts = PHOTO_GROUP_OPTIONS.filter(o => o.cat === cat &&
                    (!o.facet || facetFraction(allPersonPhotos, o.facet) >= FACET_THRESHOLD));
                if (!opts.length) continue;
                addLabel(cat);
                opts.forEach(o => addItem(o.label, o.value, currentPhotoGroup === o.value));
            }

            photoGroupPanel.classList.add('show');
            activeMenu = { element: photoGroupPanel, parent: document.getElementById('photoGroupBtn') };
            positionMenu(photoGroupPanel, document.getElementById('photoGroupBtn'));
        }

        document.getElementById('photoGroupBtn').addEventListener('click', (e) => {
            e.stopPropagation();
            if (photoGroupPanel && photoGroupPanel.classList.contains('show')) {
                closeAllMenus();
            } else {
                openPhotoGroupPanel();
            }
        });

        /**
         * Recompute column count and cell size from the grid's current width and the
         * user's grid-size setting, then set the grid's full virtual height.
         *
         * Mirrors the CSS auto-fill formula repeat(auto-fill, minmax(size, 1fr)) so
         * the layout matches what the old CSS grid produced. Cells are square to
         * match the previous aspect-ratio: 1.
         */
        function computeGridGeometry() {
            const photoGrid = document.getElementById('photoGrid');
            const total = lightboxPhotos.length;

            const width = photoGrid.clientWidth || (photoGrid.parentElement ? photoGrid.parentElement.clientWidth : 0);
            const minCell = currentGridSize;

            let cols = Math.floor((width + GRID_GAP) / (minCell + GRID_GAP));
            cols = Math.max(1, cols);

            const cellW = (width - (cols - 1) * GRID_GAP) / cols;
            const cellH = cellW;                 // square cells
            const rowH = cellH + GRID_GAP;

            gridGeom = { cols, cellW, cellH, rowH, total };

            if (gridGroups) {
                // Lay each group out as a header followed by its rows of cells (no rows
                // when collapsed). headerTop / cellsTop / rows are read back when rendering.
                let y = 0;
                for (const g of gridGroups) {
                    g.headerTop = y;
                    y += GROUP_HEADER_H;
                    g.cellsTop = y;
                    g.rows = g.collapsed ? 0 : Math.ceil(g.count / cols);
                    y += g.rows * rowH;
                }
                photoGrid.style.height = (y > 0 ? y : 0) + 'px';
            } else {
                // Full height so the scrollbar reflects every row; trailing gap removed.
                const rows = Math.ceil(total / cols);
                photoGrid.style.height = (rows > 0 ? rows * rowH - GRID_GAP : 0) + 'px';
            }
        }

        /**
         * Absolutely position a cell node for its index using the current geometry.
         */
        // The group (descriptor) a flat index belongs to, via binary search on startIndex.
        function groupOfIndex(index) {
            if (!gridGroups) return null;
            let lo = 0, hi = gridGroups.length - 1;
            while (lo <= hi) {
                const mid = (lo + hi) >> 1;
                const g = gridGroups[mid];
                if (index < g.startIndex) hi = mid - 1;
                else if (index >= g.startIndex + g.count) lo = mid + 1;
                else return g;
            }
            return null;
        }

        function positionPhotoItem(node, index) {
            const cols = gridGeom.cols;
            node.style.width = gridGeom.cellW + 'px';
            node.style.height = gridGeom.cellH + 'px';

            if (gridGroups) {
                const g = groupOfIndex(index);
                if (!g) return;
                const local = index - g.startIndex;
                const col = local % cols;
                const row = Math.floor(local / cols);
                node.style.left = (col * (gridGeom.cellW + GRID_GAP)) + 'px';
                node.style.top = (g.cellsTop + row * gridGeom.rowH) + 'px';
            } else {
                const col = index % cols;
                const row = Math.floor(index / cols);
                node.style.left = (col * (gridGeom.cellW + GRID_GAP)) + 'px';
                node.style.top = (row * gridGeom.rowH) + 'px';
            }
        }

        /**
         * Render only the cells visible in the viewport (plus a buffer of rows).
         *
         * Cells that scrolled out of the window are removed from the DOM and cells
         * that scrolled in are created, keeping the live node count bounded to
         * roughly the visible area no matter how many photos the person has.
         */
        function renderGridWindow(force) {
            if (gridGroups) { renderGroupedWindow(); return; }

            const container = document.querySelector('.photo-grid-container');
            const photoGrid = document.getElementById('photoGrid');

            // Clamp to the live list length so a stale gridGeom (list shrank or emptied,
            // e.g. a person that loaded empty during a recluster, or a filter that matched
            // nothing) can never index past lightboxPhotos and read undefined.
            const total = Math.min(gridGeom.total, lightboxPhotos.length);
            if (!container || !photoGrid || total === 0) return;

            const cols = gridGeom.cols;
            const rowH = gridGeom.rowH;

            const scrollTop = container.scrollTop;
            const viewH = container.clientHeight;

            // Index range of cells that should exist right now.
            let firstRow = Math.floor(scrollTop / rowH) - GRID_BUFFER_ROWS;
            let lastRow = Math.ceil((scrollTop + viewH) / rowH) + GRID_BUFFER_ROWS;
            firstRow = Math.max(0, firstRow);
            const firstIdx = firstRow * cols;
            let lastIdx = (lastRow + 1) * cols - 1;
            lastIdx = Math.min(total - 1, lastIdx);

            // Recycle cells that left the window.
            for (const [idx, node] of renderedItems) {
                if (idx < firstIdx || idx > lastIdx) {
                    node.remove();
                    renderedItems.delete(idx);
                }
            }

            // Create cells that entered the window.
            for (let i = firstIdx; i <= lastIdx; i++) {
                if (!renderedItems.has(i)) {
                    const node = createPhotoItem(i);
                    if (!node) continue;
                    renderedItems.set(i, node);
                    photoGrid.appendChild(node);
                }
            }
        }

        /**
         * Grouped equivalent of renderGridWindow: walks the group descriptors and renders
         * the headers and cells whose y-range intersects the viewport (plus a buffer),
         * recycling everything outside it. Cells use their flat index (into lightboxPhotos)
         * so clicks/lightbox/selection work unchanged.
         */
        function renderGroupedWindow() {
            const container = document.querySelector('.photo-grid-container');
            const photoGrid = document.getElementById('photoGrid');
            if (!container || !photoGrid || !gridGroups || lightboxPhotos.length === 0) return;

            const cols = gridGeom.cols;
            const rowH = gridGeom.rowH;
            const scrollTop = container.scrollTop;
            const viewH = container.clientHeight;
            const bufPx = GRID_BUFFER_ROWS * rowH;
            const vTop = scrollTop - bufPx;
            const vBottom = scrollTop + viewH + bufPx;

            const visibleCells = new Set();
            const visibleHeaders = new Set();

            for (let gi = 0; gi < gridGroups.length; gi++) {
                const g = gridGroups[gi];
                const blockBottom = g.cellsTop + g.rows * rowH;   // rows = 0 when collapsed
                if (blockBottom < vTop || g.headerTop > vBottom) continue;

                if (g.headerTop <= vBottom && (g.headerTop + GROUP_HEADER_H) >= vTop) {
                    visibleHeaders.add(gi);
                    if (!renderedHeaders.has(gi)) {
                        const hnode = createGroupHeader(gi);
                        renderedHeaders.set(gi, hnode);
                        photoGrid.appendChild(hnode);
                    } else {
                        renderedHeaders.get(gi).style.top = g.headerTop + 'px';
                    }
                }

                if (!g.collapsed && g.rows > 0) {
                    let firstRow = Math.max(0, Math.floor((vTop - g.cellsTop) / rowH));
                    let lastRow = Math.min(g.rows - 1, Math.floor((vBottom - g.cellsTop) / rowH));
                    for (let r = firstRow; r <= lastRow; r++) {
                        for (let c = 0; c < cols; c++) {
                            const local = r * cols + c;
                            if (local >= g.count) break;
                            const flatIdx = g.startIndex + local;
                            visibleCells.add(flatIdx);
                            if (!renderedItems.has(flatIdx)) {
                                const node = createPhotoItem(flatIdx);
                                if (!node) continue;
                                renderedItems.set(flatIdx, node);
                                photoGrid.appendChild(node);
                            }
                        }
                    }
                }
            }

            for (const [idx, node] of renderedItems) {
                if (!visibleCells.has(idx)) { node.remove(); renderedItems.delete(idx); }
            }
            for (const [gi, node] of renderedHeaders) {
                if (!visibleHeaders.has(gi)) { node.remove(); renderedHeaders.delete(gi); }
            }
        }

        /**
         * Build a collapsible group-header row (icon + label + count). Click is handled
         * by the delegated grid listener (onGridClick) via the data-gi attribute.
         */
        function createGroupHeader(gi) {
            const g = gridGroups[gi];
            const node = document.createElement('div');
            node.className = 'group-header';
            node.dataset.gi = gi;
            node.style.top = g.headerTop + 'px';
            node.style.height = GROUP_HEADER_H + 'px';
            node.innerHTML =
                `<span class="group-header-icon">${g.collapsed ? SVG_EXPAND : SVG_COLLAPSE}</span>` +
                `<span class="group-header-label"></span>` +
                `<span class="group-header-count"></span>`;
            node.querySelector('.group-header-label').textContent = g.label;
            node.querySelector('.group-header-count').textContent = `(${g.count})`;
            return node;
        }

        /**
         * Build a single photo cell (image placeholder + kebab button) for an index.
         *
         * No per-cell listeners are attached: clicks are handled by one delegated
         * listener on the grid (onGridClick) and there is a single shared context
         * menu rather than one per photo. The thumbnail is loaded lazily.
         */
        function createPhotoItem(index) {
            const photo = lightboxPhotos[index];
            if (!photo) return null;   // stale index (list changed under a render pass)

            const node = document.createElement('div');
            node.className = 'photo-item';
            node.setAttribute('data-face-id', photo.face_id);
            node.setAttribute('data-index', index);
            if (selectedPhotos.has(photo.face_id)) {
                node.classList.add('selected');
            }

            const hiddenOverlay = photo.is_hidden ? '<div class="hidden-overlay"></div>' : '';
            node.innerHTML = `
                <img class="photo-placeholder" style="width: 100%; height: 100%; object-fit: cover;">
                ${hiddenOverlay}
                <button class="kebab-menu">
                    <span class="kebab-dot"></span>
                    <span class="kebab-dot"></span>
                    <span class="kebab-dot"></span>
                </button>
            `;

            positionPhotoItem(node, index);
            loadThumb(node, photo);
            return node;
        }

        /**
         * Lazily fetch a cell's thumbnail and set it on the cell's <img>.
         *
         * Thumbnails are cached by face_id in a bounded map so scrolling back to a
         * recently seen cell is instant. The request is tagged with the current
         * gridReqSeq so a thumbnail that resolves after the user changed people or
         * view mode is dropped instead of painting into a recycled cell.
         */
        async function loadThumb(node, photo) {
            if (!photo) return;   // stale index (list changed under a render pass)
            const img = node.querySelector('img');
            if (!img) return;

            const cached = thumbCache.get(photo.face_id);
            if (cached) {
                img.src = cached;
                return;
            }

            const mySeq = gridReqSeq;
            const bbox = (gridViewMode === 'zoom_to_faces') ? photo.bbox : null;

            try {
                const dataUrl = await pywebview.api.create_thumbnail(photo.path, currentGridSize, bbox, photo.face_id);
                if (mySeq !== gridReqSeq || !dataUrl) return;
                cacheThumb(photo.face_id, dataUrl);
                // The cell may have been recycled while waiting; only paint if the
                // image is still attached to the document.
                if (img.isConnected) img.src = dataUrl;
            } catch (e) {
                // Leave the placeholder; a later scroll pass can retry.
            }
        }

        /**
         * Store a thumbnail, evicting the oldest entry when the cache is full.
         */
        function cacheThumb(faceId, dataUrl) {
            thumbCache.set(faceId, dataUrl);
            if (thumbCache.size > THUMB_CACHE_MAX) {
                const oldest = thumbCache.keys().next().value;
                thumbCache.delete(oldest);
            }
        }

        /**
         * Recompute geometry and reposition/refresh the window after the grid size
         * changes or the container is resized.
         */
        function relayoutGrid() {
            if (!lightboxPhotos.length) return;
            computeGridGeometry();
            for (const [idx, node] of renderedItems) {
                positionPhotoItem(node, idx);
            }
            if (gridGroups) {
                for (const [gi, node] of renderedHeaders) {
                    if (gridGroups[gi]) node.style.top = gridGroups[gi].headerTop + 'px';
                }
            }
            renderGridWindow(true);
        }

        // Collapse/expand a group section and re-lay-out (everything below it shifts).
        function toggleGroupCollapse(gi) {
            const g = gridGroups && gridGroups[gi];
            if (!g) return;
            if (g.collapsed) { collapsedGroups.delete(g.key); g.collapsed = false; }
            else { collapsedGroups.add(g.key); g.collapsed = true; }

            renderedItems.forEach(node => node.remove());
            renderedItems.clear();
            renderedHeaders.forEach(node => node.remove());
            renderedHeaders.clear();
            computeGridGeometry();
            renderGridWindow(true);
        }

        /**
         * Drop cached crops and reload the visible thumbnails. Used when the view
         * mode toggles between whole-photo and zoom-to-face, since the crop changes.
         */
        function refreshThumbnails() {
            thumbCache.clear();
            gridReqSeq++;   // cancel in-flight loads bound to the old view mode
            for (const [idx, node] of renderedItems) {
                loadThumb(node, lightboxPhotos[idx]);
            }
        }

        /**
         * rAF-throttled scroll handler: re-render the visible window at most once per
         * animation frame instead of on every scroll event.
         */
        function onGridScroll() {
            if (gridScrollScheduled) return;
            gridScrollScheduled = true;
            requestAnimationFrame(() => {
                gridScrollScheduled = false;
                renderGridWindow(false);
            });
        }

        /**
         * Build the HTML for the photo context menu. Matches the original options:
         * with a multi-selection only transfer + hide/unhide are offered; for a
         * single photo make-primary is added (and transfer is omitted when the photo
         * is hidden).
         */
        function buildPhotoMenuHTML(isHidden, count) {
            if (count > 0) {
                const hideItem = isHidden
                    ? `<div class="context-menu-item" data-action="unhide-photo">Unhide photo (${count} photos)</div>`
                    : `<div class="context-menu-item" data-action="hide-photo">Hide photo (${count} photos)</div>`;
                return `
                    <div class="context-menu-item" data-action="transfer-tag">Remove/Transfer Tag (${count} photos)</div>
                    ${hideItem}
                `;
            }
            if (isHidden) {
                return `
                    <div class="context-menu-item" data-action="make-primary">Make primary photo</div>
                    <div class="context-menu-item" data-action="unhide-photo">Unhide photo</div>
                `;
            }
            return `
                <div class="context-menu-item" data-action="make-primary">Make primary photo</div>
                <div class="context-menu-item" data-action="transfer-tag">Remove/Transfer Tag</div>
                <div class="context-menu-item" data-action="hide-photo">Hide photo</div>
            `;
        }

        /**
         * Open the shared context menu for a photo cell (kebab click). Sets the photo
         * context used by the menu actions and, when there is already an active
         * selection, adds the clicked photo to it (preserving the old behaviour).
         */
        function openPhotoMenu(item, index, faceId, x, y) {
            closeAllMenus();

            const photo = lightboxPhotos[index];
            currentPhotoContext = {
                person_name: currentPerson.name,
                face_id: faceId,
                path: photo.path,
                is_hidden: photo.is_hidden
            };

            // Whether a selection existed before this click decides single vs
            // multi-photo menu, matching the original logic.
            const hasSelection = selectedPhotos.size > 0;
            if (hasSelection && !selectedPhotos.has(faceId)) {
                selectedPhotos.add(faceId);
                item.classList.add('selected');
                updateSelectionInfo();
            }

            const count = hasSelection ? selectedPhotos.size : 0;
            sharedContextMenu.innerHTML = buildPhotoMenuHTML(photo.is_hidden, count);
            sharedContextMenu.classList.add('show');
            item.classList.add('menu-active');
            activeMenu = { element: sharedContextMenu, parent: item };
            // Right-click passes a cursor point; the kebab click anchors to the button.
            if (typeof x === 'number' && typeof y === 'number') {
                positionMenuAt(sharedContextMenu, x, y);
            } else {
                positionMenu(sharedContextMenu, item.querySelector('.kebab-menu'));
            }
        }

        /**
         * Delegated right-click handler for the grid: open the photo menu at the cursor.
         */
        function onGridContextMenu(e) {
            const item = e.target.closest('.photo-item');
            if (!item) return;
            e.preventDefault();
            e.stopPropagation();
            const index = parseInt(item.getAttribute('data-index'));
            const faceId = parseInt(item.getAttribute('data-face-id'));
            openPhotoMenu(item, index, faceId, e.clientX, e.clientY);
        }

        /**
         * Delegated click handler for the whole grid. Resolves which cell was clicked
         * and applies kebab / ctrl-select / shift-range / open behaviour exactly as
         * the old per-cell listeners did.
         */
        function onGridClick(e) {
            const header = e.target.closest('.group-header');
            if (header) {
                toggleGroupCollapse(parseInt(header.dataset.gi, 10));
                return;
            }

            const item = e.target.closest('.photo-item');
            if (!item) return;

            const index = parseInt(item.getAttribute('data-index'));
            const faceId = parseInt(item.getAttribute('data-face-id'));

            if (e.target.closest('.kebab-menu')) {
                e.stopPropagation();
                openPhotoMenu(item, index, faceId);
                return;
            }

            if (e.ctrlKey || e.metaKey) {
                togglePhotoSelection(faceId, index, item);
            } else if (e.shiftKey) {
                if (lastSelectedIndex >= 0) {
                    selectPhotoRange(lastSelectedIndex, index);
                } else {
                    selectedPhotos.add(faceId);
                    item.classList.add('selected');
                    lastSelectedIndex = index;
                    updateSelectionInfo();
                }
            } else {
                if (selectedPhotos.size === 0) {
                    openLightbox(index);
                } else {
                    clearSelection();
                }
            }
        }

        /**
         * Delegated double-click handler: open the photo in the OS default viewer.
         */
        function onGridDblClick(e) {
            const item = e.target.closest('.photo-item');
            if (!item || e.target.closest('.kebab-menu')) return;
            const index = parseInt(item.getAttribute('data-index'));
            pywebview.api.open_photo(lightboxPhotos[index].path);
        }

        /**
         * One-time wiring for the virtualized grid: the shared context menu, the
         * delegated click/double-click handlers, the throttled scroll handler, and a
         * ResizeObserver that relayouts when the container size changes.
         */
        function setupPhotoGrid() {
            const container = document.querySelector('.photo-grid-container');
            const photoGrid = document.getElementById('photoGrid');
            if (!container || !photoGrid) return;

            // Single context menu reused for every photo (was one per photo before).
            sharedContextMenu = document.createElement('div');
            sharedContextMenu.className = 'context-menu';
            document.body.appendChild(sharedContextMenu);

            sharedContextMenu.addEventListener('click', (e) => {
                const menuItem = e.target.closest('.context-menu-item');
                if (!menuItem) return;
                const action = menuItem.getAttribute('data-action');
                if (action === 'make-primary') makePrimaryPhoto();
                else if (action === 'hide-photo') hidePhotos();
                else if (action === 'unhide-photo') unhidePhotos();
                else if (action === 'transfer-tag') openTransferDialog();
            });

            photoGrid.addEventListener('click', onGridClick);
            photoGrid.addEventListener('dblclick', onGridDblClick);
            photoGrid.addEventListener('contextmenu', onGridContextMenu);
            container.addEventListener('scroll', onGridScroll, { passive: true });

            // Recompute columns/cell size when the grid is resized, throttled to one
            // pass per animation frame.
            let resizeScheduled = false;
            const resizeObserver = new ResizeObserver(() => {
                if (resizeScheduled) return;
                resizeScheduled = true;
                requestAnimationFrame(() => {
                    resizeScheduled = false;
                    relayoutGrid();
                });
            });
            resizeObserver.observe(container);
        }
        
        function openLightbox(index) {
            lightboxCurrentIndex = index;
            applyPhotoDetailsVisibility();
            updateLightbox();
            document.getElementById('lightboxOverlay').classList.add('active');
            document.getElementById('appContainer').classList.add('blurred');
        }

        // Show/hide the details panel per showPhotoDetails. Off => collapse the grid to
        // a single image column and hide the panel (via .no-details on the content).
        function applyPhotoDetailsVisibility() {
            document.getElementById('lightboxContent')
                .classList.toggle('no-details', !showPhotoDetails);
        }

        // Entry point for the future GUI toggle: update state, persist, reflow, and -
        // if turning on while a photo is open - fill the panel for the current photo.
        async function setShowPhotoDetails(enabled) {
            showPhotoDetails = enabled;
            try { await pywebview.api.set_show_photo_details(enabled); } catch (err) {}
            applyPhotoDetailsVisibility();
            if (enabled && document.getElementById('lightboxOverlay').classList.contains('active')) {
                renderPhotoDetails(lightboxPhotos[lightboxCurrentIndex], lightboxCurrentIndex);
            }
        }

        function closeLightbox() {
            const overlayContainer = document.getElementById('faceTagsOverlay');
            overlayContainer.innerHTML = '';
            overlayContainer.style.width = '0';
            overlayContainer.style.height = '0';
            
            document.getElementById('lightboxOverlay').classList.remove('active');
            document.getElementById('appContainer').classList.remove('blurred');
        }

        function nextLightboxImage() {
            if (lightboxCurrentIndex < lightboxPhotos.length - 1) {
                lightboxCurrentIndex++;
                updateLightbox();
            }
        }

        function prevLightboxImage() {
            if (lightboxCurrentIndex > 0) {
                lightboxCurrentIndex--;
                updateLightbox();
            }
        }

        function drawFaceTags(faces, imageElement) {
            const overlayContainer = document.getElementById('faceTagsOverlay');
            overlayContainer.innerHTML = '';
            
            const imgRect = imageElement.getBoundingClientRect();
            // Overlay lives inside the image pane now (F4), so position it relative to
            // the pane's box, not the whole lightbox content grid.
            const contentRect = document.getElementById('lightboxImagePane').getBoundingClientRect();
            
            const naturalWidth = imageElement.naturalWidth;
            const naturalHeight = imageElement.naturalHeight;
            
            const imageAspect = naturalWidth / naturalHeight;
            const containerAspect = imgRect.width / imgRect.height;
            
            let displayWidth, displayHeight, offsetX, offsetY;
            
            if (imageAspect > containerAspect) {
                displayWidth = imgRect.width;
                displayHeight = imgRect.width / imageAspect;
                offsetX = 0;
                offsetY = (imgRect.height - displayHeight) / 2;
            } else {
                displayHeight = imgRect.height;
                displayWidth = imgRect.height * imageAspect;
                offsetX = (imgRect.width - displayWidth) / 2;
                offsetY = 0;
            }
            
            overlayContainer.style.width = displayWidth + 'px';
            overlayContainer.style.height = displayHeight + 'px';
            overlayContainer.style.left = (imgRect.left - contentRect.left + offsetX) + 'px';
            overlayContainer.style.top = (imgRect.top - contentRect.top + offsetY) + 'px';
            
            const scaleX = displayWidth / naturalWidth;
            const scaleY = displayHeight / naturalHeight;
            
            faces.forEach(face => {
                if (!face.tag_name) return;
                
                const x1 = face.bbox_x1 * scaleX;
                const y1 = face.bbox_y1 * scaleY;
                const x2 = face.bbox_x2 * scaleX;
                const y2 = face.bbox_y2 * scaleY;
                
                const width = x2 - x1;
                const height = y2 - y1;
                
                const box = document.createElement('div');
                box.className = 'face-tag-box';
                box.style.left = x1 + 'px';
                box.style.top = y1 + 'px';
                box.style.width = width + 'px';
                box.style.height = height + 'px';
                
                const label = document.createElement('div');
                label.className = 'face-tag-label';
                label.textContent = face.tag_name;
                box.appendChild(label);
                
                overlayContainer.appendChild(box);
            });
        }

        // Minimal HTML escape for values rendered into the details panel (paths,
        // EXIF strings) so a stray <, > or & can't break the markup.
        function escapeHtml(s) {
            return String(s)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;')
                .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        // Fetch and render the F4 details panel for the photo at reqIndex. Guards on
        // reqIndex so a fast prev/next doesn't render stale details over the new photo.
        async function renderPhotoDetails(photo, reqIndex) {
            const rowsEl = document.getElementById('lightboxDetailsRows');
            rowsEl.scrollTop = 0;
            rowsEl.innerHTML = '';
            try {
                const details = await pywebview.api.get_photo_details(photo.path);
                if (reqIndex !== lightboxCurrentIndex) return;
                rowsEl.innerHTML = details.map(([label, value]) =>
                    `<div class="lightbox-detail-row">` +
                    `<div class="lightbox-detail-label">${escapeHtml(label)}</div>` +
                    `<div class="lightbox-detail-value">${escapeHtml(value)}</div>` +
                    `</div>`
                ).join('');
            } catch (error) {
                console.error('Error loading photo details:', error);
            }
        }

        async function updateLightbox() {
            const reqIndex = lightboxCurrentIndex;
            const photo = lightboxPhotos[lightboxCurrentIndex];
            document.getElementById('lightboxCounter').textContent = `${lightboxCurrentIndex + 1} of ${lightboxPhotos.length}`;

            document.getElementById('lightboxPrev').style.display = lightboxCurrentIndex > 0 ? 'flex' : 'none';
            document.getElementById('lightboxNext').style.display = lightboxCurrentIndex < lightboxPhotos.length - 1 ? 'flex' : 'none';
            
            const overlayContainer = document.getElementById('faceTagsOverlay');
            overlayContainer.innerHTML = '';
            overlayContainer.style.width = '0';
            overlayContainer.style.height = '0';
            
            try {
                const lightboxImage = document.getElementById('lightboxImage');
                
                if (showFaceTagsPreview) {
                    const result = await pywebview.api.get_photo_face_tags(photo.path);
                    
                    const fullSizePreview = await pywebview.api.get_full_size_preview(photo.path);
                    
                    if (fullSizePreview) {
                        lightboxImage.src = fullSizePreview;
                    } else {
                        lightboxImage.src = (thumbCache.get(photo.face_id) || '');
                    }
                    
                    lightboxImage.onload = () => {
                        if (result.success && result.faces.length > 0) {
                            drawFaceTags(result.faces, lightboxImage);
                        }
                    };
                } else {
                    const fullSizePreview = await pywebview.api.get_full_size_preview(photo.path);
                    if (fullSizePreview) {
                        lightboxImage.src = fullSizePreview;
                    } else {
                        lightboxImage.src = (thumbCache.get(photo.face_id) || '');
                    }
                    lightboxImage.onload = null;
                }
            } catch (error) {
                console.error('Error loading full size preview:', error);
                document.getElementById('lightboxImage').src = (thumbCache.get(photo.face_id) || '');
            }

            if (showPhotoDetails) {
                renderPhotoDetails(photo, reqIndex);
            }
        }

        document.getElementById('lightboxClose').addEventListener('click', closeLightbox);

        document.getElementById('lightboxOverlay').addEventListener('click', (e) => {
            if (e.target === document.getElementById('lightboxOverlay')) {
                closeLightbox();
            }
        });

        document.getElementById('lightboxPrev').addEventListener('click', (e) => {
            e.stopPropagation();
            prevLightboxImage();
        });

        document.getElementById('lightboxNext').addEventListener('click', (e) => {
            e.stopPropagation();
            nextLightboxImage();
        });

        document.getElementById('lightboxOpenExternal').addEventListener('click', () => {
            const photo = lightboxPhotos[lightboxCurrentIndex];
            pywebview.api.open_photo(photo.path);
        });

        document.addEventListener('keydown', (e) => {
            const lightboxOverlay = document.getElementById('lightboxOverlay');
            
            if (lightboxOverlay.classList.contains('active')) {
                if (e.key === 'Escape') {
                    closeLightbox();
                } else if (e.key === 'ArrowLeft') {
                    prevLightboxImage();
                } else if (e.key === 'ArrowRight') {
                    nextLightboxImage();
                }
            } else if (e.key === 'Escape' && selectedPhotos.size > 0) {
                clearSelection();
            } else if (e.key === 'Escape' && selectedPeople.size > 0) {
                clearPeopleSelection();
            }
        });

        async function openTransferDialog() {
            if (!currentPhotoContext && selectedPhotos.size === 0) {
                console.error('No photo context or selection');
                addLogEntry('ERROR: No photo context available');
                closeAllMenus();
                return;
            }
            
            const faceIds = selectedPhotos.size > 0 ? Array.from(selectedPhotos) : [currentPhotoContext.face_id];

            if (!faceIds.length) {
                console.error('No face IDs available');
                addLogEntry('ERROR: Invalid photo context');
                closeAllMenus();
                return;
            }

            // Expand to all faces of this person in each deduped photo so a transfer
            // moves the whole photo, leaving no stray face behind (F3).
            transferContext = {
                face_ids: collectGroupFaceIds(faceIds),
                current_person: currentPhotoContext.person_name
            };
            
            closeAllMenus();
            
            try {
                if (!currentPerson || !currentPerson.clustering_id) {
                    addLogEntry('ERROR: No current person selected');
                    return;
                }
                
                const result = await pywebview.api.get_named_people_for_transfer(currentPerson.clustering_id);
                
                if (result.success) {
                    showTransferDialog(result.people);
                } else {
                    addLogEntry('ERROR: Failed to load people list - ' + result.message);
                }
            } catch (error) {
                console.error('Error loading people for transfer:', error);
                addLogEntry('Error loading people for transfer: ' + error);
            }
        }
        
        function showTransferDialog(people) {
            const transferList = document.getElementById('transferList');
            transferList.innerHTML = '';
            
            const faceCount = transferContext.face_ids.length;
            const countText = faceCount > 1 ? ` (${faceCount} photos)` : '';
            
            const removeOption = document.createElement('div');
            removeOption.className = 'transfer-option remove';
            removeOption.textContent = `Remove from this person${countText}`;
            removeOption.addEventListener('click', () => {
                executeRemoveFaces();
            });
            transferList.appendChild(removeOption);
            
            people.forEach(person => {
                const option = document.createElement('div');
                option.className = 'transfer-option';
                option.textContent = `Transfer to ${person.name}${countText}`;
                option.addEventListener('click', () => {
                    executeTransferFaces(person.name);
                });
                transferList.appendChild(option);
            });
            
            document.getElementById('transferOverlay').classList.add('active');
            document.getElementById('appContainer').classList.add('blurred');
        }
        
        function closeTransferDialog() {
            document.getElementById('transferOverlay').classList.remove('active');
            document.getElementById('appContainer').classList.remove('blurred');
            transferContext = null;
        }
        
        async function executeRemoveFaces() {
            if (!transferContext) return;
            
            const faceIds = transferContext.face_ids;
            const personName = transferContext.current_person;
            
            closeTransferDialog();
            
            try {
                if (!currentPerson || !currentPerson.clustering_id) {
                    addLogEntry('ERROR: No current person selected');
                    return;
                }
                
                for (const faceId of faceIds) {
                    await pywebview.api.remove_face_to_unmatched(currentPerson.clustering_id, faceId);
                }
                
                addLogEntry(`${faceIds.length} face(s) moved from ${personName} to Unmatched Faces`);
                clearSelection();
            } catch (error) {
                console.error('Error removing faces:', error);
                addLogEntry('Error removing faces: ' + error);
            }
        }

        async function executeTransferFaces(targetName) {
            if (!transferContext) return;
            
            const faceIds = transferContext.face_ids;
            const sourceName = transferContext.current_person;
            
            closeTransferDialog();
            
            try {
                if (!currentPerson || !currentPerson.clustering_id) {
                    addLogEntry('ERROR: No current person selected');
                    return;
                }
                
                for (const faceId of faceIds) {
                    await pywebview.api.transfer_face_to_person(currentPerson.clustering_id, faceId, targetName);
                }
                
                addLogEntry(`${faceIds.length} face(s) transferred from ${sourceName} to ${targetName}`);
                clearSelection();
            } catch (error) {
                console.error('Error transferring faces:', error);
                addLogEntry('Error transferring faces: ' + error);
            }
        }

        document.getElementById('transferCancelBtn').addEventListener('click', closeTransferDialog);
        
        document.getElementById('transferOverlay').addEventListener('click', (e) => {
            if (e.target === document.getElementById('transferOverlay')) {
                closeTransferDialog();
            }
        });

        async function reloadCurrentPhotos() {
            // Re-fetch and re-render the current person's grid (for example after a
            // setting that changes which photos are shown, like show-hidden).
            if (currentPerson) {
                await loadPersonPhotos(currentPerson.clustering_id, currentPerson.id);
            }
        }

        function updateStatusMessage(message) {
            // Only drive the status line. The message already reaches the log viewer
            // through the backend logger -> GuiLogHandler -> appendBackendLog path, so
            // appending here too would double every status line.
            document.getElementById('progressText').textContent = message;
        }

        // Append one line to the in-app log viewer. The line is already fully formatted
        // by the backend logger (timestamp, level, name), so it is rendered verbatim and
        // the GUI log matches the console/file. Called by the backend GuiLogHandler (via
        // api._push_log_to_gui), so it must NOT mirror back to log_message or it would loop.
        function appendBackendLog(text) {
            const logViewer = document.getElementById('logViewer');
            if (!logViewer) return;
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.textContent = text;
            logViewer.appendChild(entry);
            logViewer.scrollTop = logViewer.scrollHeight;
        }

        // Show/hide the progress bar and swap the status text (Phase 1): while a scan or
        // export runs the progress text occupies the status line in place of the face
        // count; when it ends the face count returns.
        function setProgressVisible(visible) {
            document.getElementById('progressBar').style.display = visible ? 'block' : 'none';
            document.getElementById('progressText').style.display = visible ? 'inline' : 'none';
            document.getElementById('faceCount').style.display = visible ? 'none' : 'inline';
        }

        function updateProgress(current, total, percent, label) {
            document.getElementById('progressFill').style.width = percent + '%';
            document.getElementById('progressText').textContent = `${label || 'Scanning'}: ${current}/${total}`;
        }

        function hideProgress() {
            setProgressVisible(false);
            updateFaceCount();
        }

        async function updateFaceCount() {
            try {
                const sysInfo = await pywebview.api.get_system_info();
                document.getElementById('faceCount').textContent = `Found: ${sysInfo.total_faces} faces`;
            } catch (error) {
                console.error('Error updating face count:', error);
            }
        }

        // Log a frontend-originated event. It's sent to the backend logger, which both
        // writes the persistent file log and echoes it back into the in-app log viewer
        // via appendBackendLog - so there's a single, unified path into the log (no
        // direct DOM write here, which would duplicate the echoed line). Guarded and
        // fire-and-forget: the bridge may not exist yet during early startup.
        function addLogEntry(message) {
            if (window.pywebview && window.pywebview.api && window.pywebview.api.log_message) {
                try { window.pywebview.api.log_message('INFO', message); } catch (e) {}
            }
        }

        // Surface otherwise-silent JS errors and promise rejections into the log so
        // frontend-only bugs (no Python traceback) are visible. Writes straight to the
        // bridge (not addLogEntry) to avoid any chance of a logging recursion.
        function logJsFailure(tag, msg) {
            const line = '[' + tag + '] ' + msg;
            console.error(line);
            if (window.pywebview && window.pywebview.api && window.pywebview.api.log_message) {
                try { window.pywebview.api.log_message('ERROR', line); } catch (e) {}
            }
        }
        window.addEventListener('error', (ev) => {
            logJsFailure('JSERROR', (ev.message || 'error') + ' @ ' + (ev.filename || '') + ':' + (ev.lineno || ''));
        });
        window.addEventListener('unhandledrejection', (ev) => {
            const r = ev.reason;
            logJsFailure('JSREJECT', r && r.message ? r.message : String(r));
        });



        async function loadAllSettings() {
            try {
                const threshold = await pywebview.api.get_threshold();
                document.getElementById('thresholdSlider').value = threshold;
                document.getElementById('thresholdValue').textContent = threshold + '%';
                
                const scanFrequency = await pywebview.api.get_scan_frequency();
                document.getElementById('scanFrequencyDropdown').value = scanFrequency;

                const logLevel = await pywebview.api.get_log_level();
                document.getElementById('logLevelDropdown').value = logLevel;

                currentPhotoSort = await pywebview.api.get_photo_sort_mode();
                buildSortOptions();

                currentPhotoGroup = await pywebview.api.get_photo_group_mode();

                const closeToTray = await pywebview.api.get_close_to_tray();
                document.getElementById('closeToTrayToggle').checked = closeToTray;
                
                const dynamicResources = await pywebview.api.get_dynamic_resources();
                document.getElementById('dynamicResourcesToggle').checked = dynamicResources;
                
                const showUnmatchedSetting = await pywebview.api.get_show_unmatched();
                showUnmatched = showUnmatchedSetting;
                document.getElementById('showUnmatchedToggle').checked = showUnmatchedSetting;
                
                const showHiddenSetting = await pywebview.api.get_show_hidden();
                showHidden = showHiddenSetting;
                document.getElementById('showHiddenToggle').checked = showHiddenSetting;
                
                const showHiddenPhotosSetting = await pywebview.api.get_show_hidden_photos();
                showHiddenPhotos = showHiddenPhotosSetting;
                document.getElementById('showHiddenPhotosToggle').checked = showHiddenPhotosSetting;
                
                const showDevOptionsSetting = await pywebview.api.get_show_dev_options();
                showDevOptions = showDevOptionsSetting;
                document.getElementById('showDevOptionsToggle').checked = showDevOptionsSetting;
                
                const minPhotosEnabledSetting = await pywebview.api.get_min_photos_enabled();
                minPhotosEnabled = minPhotosEnabledSetting;
                document.getElementById('minPhotosToggle').checked = minPhotosEnabledSetting;
                
                const minPhotosCountSetting = await pywebview.api.get_min_photos_count();
                minPhotosCount = minPhotosCountSetting;
                document.getElementById('minPhotosInput').value = minPhotosCountSetting;
                document.getElementById('minPhotosInput').disabled = !minPhotosEnabledSetting;
                
                const hideUnnamedSetting = await pywebview.api.get_hide_unnamed_persons();
                hideUnnamedPersons = hideUnnamedSetting;
                document.getElementById('hideUnnamedToggle').checked = hideUnnamedSetting;
                
                const showFaceTagsPreviewSetting = await pywebview.api.get_show_face_tags_preview();
                showFaceTagsPreview = showFaceTagsPreviewSetting;
                document.getElementById('showFaceTagsPreviewToggle').addEventListener('change', async (e) => {
                    showFaceTagsPreview = e.target.checked;
                    await pywebview.api.set_show_face_tags_preview(showFaceTagsPreview);
                    
                    if (document.getElementById('lightboxOverlay').classList.contains('active')) {
                        await updateLightbox();
                    }
                    
                    addLogEntry('Show face tags in preview: ' + (showFaceTagsPreview ? 'enabled' : 'disabled'));
                });

                // F4: load the details-panel visibility. No GUI control yet - a toggle
                // will call setShowPhotoDetails() later; applyPhotoDetailsVisibility runs
                // when the lightbox opens.
                showPhotoDetails = await pywebview.api.get_show_photo_details();

                const gridSize = await pywebview.api.get_grid_size();
                document.getElementById('sizeSlider').value = gridSize;
                currentGridSize = parseInt(gridSize);   // virtualizer reads this for the cell size
                
                const viewMode = await pywebview.api.get_view_mode();
                document.getElementById('viewModeDropdown').value = viewMode;
                gridViewMode = viewMode;   // controls whole-photo vs zoom-to-face thumbnails
                
                const sortMode = await pywebview.api.get_sort_mode();
                currentSortMode = sortMode;
                updateJumpToButtonVisibility();
                
                includeFolders = await pywebview.api.get_include_folders();
                renderIncludeFolders();
                
                excludeFolders = await pywebview.api.get_exclude_folders();
                renderExcludeFolders();
                
                const wildcards = await pywebview.api.get_wildcard_exclusions();
                document.getElementById('wildcardInput').value = wildcards;
                
                await updateCacheSize();

                addLogEntry('Settings loaded successfully');
            } catch (error) {
                console.error('Error loading settings:', error);
                addLogEntry('ERROR: Failed to load settings - ' + error);
            }
        }


        document.getElementById('logLevelDropdown').addEventListener('change', async (e) => {
            const level = e.target.value;
            try {
                await pywebview.api.set_log_level(level);
                addLogEntry('Log detail set to: ' + (level === 'DEBUG' ? 'Debug' : 'Normal'));
            } catch (error) {
                console.error('Error setting log level:', error);
            }
        });

        document.getElementById('scanFrequencyDropdown').addEventListener('change', async (e) => {
            const frequency = e.target.value;
            try {
                await pywebview.api.set_scan_frequency(frequency);
                
                const frequencyNames = {
                    'every_restart': 'every restart',
                    'restart_1_day': 'restart after 1 day',
                    'restart_1_week': 'restart after 1 week',
                    'manual': 'manually'
                };
                
                addLogEntry('Scan frequency changed to: ' + frequencyNames[frequency]);
                
                if (frequency === 'manual') {
                    addLogEntry('Note: You must manually rescan from Folders to Scan settings');
                }
            } catch (error) {
                console.error('Error changing scan frequency:', error);
                addLogEntry('ERROR: Failed to change scan frequency - ' + error);
            }
        });

        document.getElementById('hideUnnamedToggle').addEventListener('change', async (e) => {
            hideUnnamedPersons = e.target.checked;
            await pywebview.api.set_hide_unnamed_persons(hideUnnamedPersons);
            await loadPeople();
            addLogEntry('Hide unnamed persons: ' + (hideUnnamedPersons ? 'enabled' : 'disabled'));
        });

        function updateJumpToButtonVisibility() {
            const jumpToBtn = document.getElementById('jumpToBtn');
            if (currentSortMode.startsWith('names_')) {
                jumpToBtn.style.display = 'flex';
            } else {
                jumpToBtn.style.display = 'none';
                if (isAlphabetMode) {
                    isAlphabetMode = false;
                    renderPeopleList();
                }
            }
        }

        function checkNoFolders() {
            const folders = includeFolders || [];
            if (folders.length === 0) {
                document.getElementById('noFoldersOverlay').classList.add('active');
                document.getElementById('appContainer').classList.add('blurred');
            }
        }

        function closeNoFoldersOverlay() {
            document.getElementById('noFoldersOverlay').classList.remove('active');
            document.getElementById('appContainer').classList.remove('blurred');
        }

        // The virtualized grid (see the grid module above) manages its own
        // scrolling, resizing, click handling, and context menu. Wire it up once.
        setupPhotoGrid();

        async function initialize() {
            try {
                // Pull everything logged before the GUI existed (startup + early backend
                // lines) and render it, then live lines follow via appendBackendLog. This
                // also activates live forwarding, so do it before anything else logs.
                try {
                    const history = await pywebview.api.get_log_history();
                    if (Array.isArray(history)) history.forEach(line => appendBackendLog(line));
                } catch (e) {
                    console.error('Log history load failed:', e);
                }

                addLogEntry('Application started');

                const sysInfo = await pywebview.api.get_system_info();
                // PyTorch/GPU/CUDA badges were removed from the bottom bar (Phase 1); the
                // info still goes to the log, and CUDA is shown in Settings -> About.
                document.getElementById('faceCount').textContent = `Found: ${sysInfo.total_faces} faces`;

                addLogEntry(`System: PyTorch ${sysInfo.pytorch_version}, ${sysInfo.gpu_available ? 'GPU' : 'CPU'}, CUDA ${sysInfo.cuda_version}`);
                
                await loadAllSettings();
                
                checkNoFolders();

                // Only reveal the progress bar if a scan actually starts. The
                // backend returns needs_scan=false when there are no folders to
                // scan, or when a scheduled scan is skipped, so the bar stays
                // hidden during an ordinary startup instead of showing a stalled
                // bar with nothing to do.
                const state = await pywebview.api.check_initial_state();

                if (state && state.needs_scan) {
                    setProgressVisible(true);
                    updateStatusMessage('Checking for new photos...');
                }
            } catch (error) {
                console.error('Initialization error:', error);
                addLogEntry('ERROR: Initialization failed - ' + error);
            }
        }

        document.getElementById('minPhotosToggle').addEventListener('change', async (e) => {
            minPhotosEnabled = e.target.checked;
            document.getElementById('minPhotosInput').disabled = !minPhotosEnabled;
            await pywebview.api.set_min_photos_enabled(minPhotosEnabled);
            
            if (isAlphabetMode) {
                renderAlphabetList();
            } else {
                renderPeopleList();
            }
            
            addLogEntry('Minimum photos filter: ' + (minPhotosEnabled ? `enabled (${minPhotosCount} photos)` : 'disabled'));
        });

        document.getElementById('minPhotosInput').addEventListener('change', async (e) => {
            const value = parseInt(e.target.value);
            if (value >= 0 && value <= 999) {
                minPhotosCount = value;
                await pywebview.api.set_min_photos_count(minPhotosCount);
                
                if (isAlphabetMode) {
                    renderAlphabetList();
                } else {
                    renderPeopleList();
                }
                
                addLogEntry(`Minimum photos threshold changed to: ${minPhotosCount}`);
            }
        });

        document.getElementById('filterBtn').addEventListener('click', () => {
            closeAllMenus();
            
            const filterMenu = document.createElement('div');
            filterMenu.className = 'context-menu';
            filterMenu.innerHTML = `
                <div class="context-menu-item" data-sort="names_asc">By Names (A to Z)</div>
                <div class="context-menu-item" data-sort="names_desc">By Names (Z to A)</div>
                <div class="context-menu-item" data-sort="photos_asc">By Photos (Low to High)</div>
                <div class="context-menu-item" data-sort="photos_desc">By Photos (High to Low)</div>
            `;
            
            document.body.appendChild(filterMenu);
            
            filterMenu.classList.add('show');
            
            const filterBtn = document.getElementById('filterBtn');
            activeMenu = { element: filterMenu, parent: filterBtn };
            
            positionMenu(filterMenu, filterBtn);
            
            filterMenu.addEventListener('click', async (e) => {
                const menuItem = e.target.closest('.context-menu-item');
                if (menuItem) {
                    const sortMode = menuItem.getAttribute('data-sort');
                    currentSortMode = sortMode;
                    await pywebview.api.set_sort_mode(sortMode);
                    
                    const sortNames = {
                        'names_asc': 'By Names (A to Z)',
                        'names_desc': 'By Names (Z to A)',
                        'photos_asc': 'By Photos (Low to High)',
                        'photos_desc': 'By Photos (High to Low)'
                    };
                    addLogEntry('Sort changed to: ' + sortNames[sortMode]);
                    
                    updateJumpToButtonVisibility();
                    renderPeopleList();
                    closeAllMenus();
                }
            });
        });

        document.getElementById('jumpToBtn').addEventListener('click', () => {
            if (currentSortMode.startsWith('names_')) {
                isAlphabetMode = !isAlphabetMode;
                const jumpToBtn = document.getElementById('jumpToBtn');
                
                if (isAlphabetMode) {
                    jumpToBtn.classList.add('active');
                    renderAlphabetList();
                    addLogEntry('Alphabet navigation enabled');
                } else {
                    jumpToBtn.classList.remove('active');
                    renderPeopleList();
                    addLogEntry('Alphabet navigation disabled');
                }
            }
        });

        document.getElementById('sizeSlider').addEventListener('input', (e) => {
            const size = parseInt(e.target.value);
            currentGridSize = size;                  // update virtualizer cell size
            pywebview.api.set_grid_size(size);
            relayoutGrid();                          // re-flow the virtualized grid
        });

        document.getElementById('viewModeDropdown').addEventListener('change', async (e) => {
            const mode = e.target.value;
            try {
                await pywebview.api.set_view_mode(mode);
                gridViewMode = mode;     // switch thumbnails between whole-photo and zoom
                refreshThumbnails();     // reload the visible crops for the new mode
                const modeName = mode === 'entire_photo' ? 'entire photo' : 'zoomed to faces';
                addLogEntry(`View mode changed to: ${modeName}`);
            } catch (error) {
                console.error('Error changing view mode:', error);
                addLogEntry('ERROR: Failed to change view mode - ' + error);
            }
        });

        const appContainer = document.getElementById('appContainer');
        const settingsOverlay = document.getElementById('settingsOverlay');
        const settingsContainer = document.getElementById('settingsContainer');
        const openSettingsBtn = document.getElementById('openSettingsBtn');
        const closeSettingsBtn = document.getElementById('closeSettingsBtn');

        function openSettings() {
            settingsOverlay.classList.add('active');
            appContainer.classList.add('blurred');
        }

        function closeSettings() {
            settingsOverlay.classList.remove('active');
            appContainer.classList.remove('blurred');
        }

        openSettingsBtn.addEventListener('click', openSettings);
        closeSettingsBtn.addEventListener('click', closeSettings);

        settingsOverlay.addEventListener('click', (e) => {
            if (e.target === settingsOverlay) {
                closeSettings();
            }
        });

        settingsContainer.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && settingsOverlay.classList.contains('active')) {
                closeSettings();
            }
        });

        const noFoldersOverlay = document.getElementById('noFoldersOverlay');
        const noFoldersContainer = document.getElementById('noFoldersContainer');
        const goToFoldersBtn = document.getElementById('goToFoldersBtn');

        goToFoldersBtn.addEventListener('click', () => {
            closeNoFoldersOverlay();
            openSettings();
            
            document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
            document.querySelector('[data-panel="folders"]').classList.add('active');
            
            document.querySelectorAll('.content-panel').forEach(panel => panel.classList.remove('active'));
            document.getElementById('folders-panel').classList.add('active');
        });

        noFoldersOverlay.addEventListener('click', (e) => {
            if (e.target === noFoldersOverlay) {
                closeNoFoldersOverlay();
            }
        });

        noFoldersContainer.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        const helpOverlay = document.getElementById('helpOverlay');
        const helpContainer = document.getElementById('helpContainer');
        const openHelpBtn = document.getElementById('openHelpBtn');
        const closeHelpBtn = document.getElementById('closeHelpBtn');

        function openHelp() {
            helpOverlay.classList.add('active');
            appContainer.classList.add('blurred');
        }

        function closeHelp() {
            helpOverlay.classList.remove('active');
            appContainer.classList.remove('blurred');
        }

        openHelpBtn.addEventListener('click', openHelp);
        closeHelpBtn.addEventListener('click', closeHelp);

        helpOverlay.addEventListener('click', (e) => {
            if (e.target === helpOverlay) {
                closeHelp();
            }
        });

        helpContainer.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && helpOverlay.classList.contains('active')) {
                closeHelp();
            }
        });

        const navItems = document.querySelectorAll('.nav-item');
        const panels = document.querySelectorAll('.content-panel');
        const thresholdSlider = document.getElementById('thresholdSlider');
        const thresholdValue = document.getElementById('thresholdValue');

        navItems.forEach(item => {
            item.addEventListener('click', () => {
                navItems.forEach(nav => nav.classList.remove('active'));
                item.classList.add('active');
                
                const panelId = item.getAttribute('data-panel') + '-panel';
                panels.forEach(panel => panel.classList.remove('active'));
                document.getElementById(panelId).classList.add('active');

                if (item.getAttribute('data-panel') === 'general') {
                updateCacheSize(); }

                if (item.getAttribute('data-panel') === 'export') {
                    loadExportPeople();
                }
            });
        });

        thresholdSlider.addEventListener('input', (e) => {
            thresholdValue.textContent = e.target.value + '%';
            pywebview.api.set_threshold(parseInt(e.target.value));
        });

        document.getElementById('recalibrateBtn').addEventListener('click', async () => {
            const threshold = parseInt(thresholdSlider.value);
            updateStatusMessage('Starting recalibration...');
            setProgressVisible(true);
            closeSettings();
            await pywebview.api.recalibrate(threshold);
        });

        document.getElementById('showUnmatchedToggle').addEventListener('change', (e) => {
            showUnmatched = e.target.checked;
            pywebview.api.set_show_unmatched(e.target.checked);
            if (isAlphabetMode) {
                renderAlphabetList();
            } else {
                renderPeopleList();
            }
            addLogEntry('Show unmatched faces: ' + (e.target.checked ? 'enabled' : 'disabled'));
        });

        document.getElementById('showHiddenToggle').addEventListener('change', async (e) => {
            showHidden = e.target.checked;
            await pywebview.api.set_show_hidden(e.target.checked);
            await loadPeople();
            addLogEntry('Show hidden persons: ' + (e.target.checked ? 'enabled' : 'disabled'));
        });

        document.getElementById('showHiddenPhotosToggle').addEventListener('change', async (e) => {
            showHiddenPhotos = e.target.checked;
            await pywebview.api.set_show_hidden_photos(e.target.checked);
            await reloadCurrentPhotos();
            addLogEntry('Show hidden photos: ' + (e.target.checked ? 'enabled' : 'disabled'));
        });

        document.getElementById('showDevOptionsToggle').addEventListener('change', async (e) => {
            showDevOptions = e.target.checked;
            await pywebview.api.set_show_dev_options(e.target.checked);
            await loadPeople();
            addLogEntry('Show development options: ' + (e.target.checked ? 'enabled' : 'disabled'));
        });

        document.getElementById('closeToTrayToggle').addEventListener('change', (e) => {
            pywebview.api.set_close_to_tray(e.target.checked);
            if (e.target.checked) {
                addLogEntry('Close to tray enabled - tray icon started');
            } else {
                addLogEntry('Close to tray disabled - tray icon removed');
            }
        });

        document.getElementById('dynamicResourcesToggle').addEventListener('change', (e) => {
            pywebview.api.set_dynamic_resources(e.target.checked);
            if (e.target.checked) {
                addLogEntry('Dynamic resource management enabled - will throttle CPU to 5% when in background');
            } else {
                addLogEntry('Dynamic resource management disabled - full speed processing');
            }
        });

        document.getElementById('saveLogBtn').addEventListener('click', async () => {
            const logViewer = document.getElementById('logViewer');
            const logContent = logViewer.innerText;
            
            try {
                const result = await pywebview.api.save_log(logContent);
                if (result.success) {
                    addLogEntry('Log saved to: ' + result.path);
                } else if (result.message !== 'Save cancelled') {
                    addLogEntry('Error saving log: ' + result.message);
                }
            } catch (error) {
                console.error('Error saving log:', error);
                addLogEntry('Error saving log: ' + error);
            }
        });

        // Photo export (F1). Copies a person's photos, or all named people, into
        // per-person subfolders under a destination the user picks. The backend
        // ExportWorker does the work and reports back via showExportComplete().
        let isExporting = false;

        function startExportUI(label) {
            isExporting = true;
            setProgressVisible(true);
            document.getElementById('progressFill').style.width = '0%';
            document.getElementById('progressText').textContent = (label || 'Exporting') + '...';
            const cancelBtn = document.getElementById('exportCancelBtn');
            cancelBtn.style.display = 'inline-flex';
            cancelBtn.disabled = false;
        }

        function endExportUI() {
            isExporting = false;
            document.getElementById('exportCancelBtn').style.display = 'none';
            // No clustering runs after an export, so hide the shared progress bar here.
            setProgressVisible(false);
        }

        let pendingExport = null;  // { label, startFn } awaiting destination-warning confirmation

        // Export mode (copy / hardlink) is chosen once in the Export Photos panel and
        // shared by every export path. Defaults to copy if the dropdown isn't present.
        function getExportMode() {
            const dropdown = document.getElementById('exportModeDropdown');
            return dropdown ? dropdown.value : 'copy';
        }

        async function exportPerson(clusteringId, personId, name) {
            closeAllMenus();
            const dest = await pywebview.api.select_folder();
            if (!dest) return;
            const mode = getExportMode();
            await beginExport(`Exporting ${name}`, dest,
                () => pywebview.api.export_person_photos(clusteringId, personId, dest, mode));
        }

        async function exportAllNamed() {
            const dest = await pywebview.api.select_folder();
            if (!dest) return;
            const mode = getExportMode();
            await beginExport('Exporting all named people', dest,
                () => pywebview.api.export_all_named(dest, mode));
        }

        // Runs destination pre-flight checks; warns and waits for confirmation if the
        // destination is risky, otherwise starts the export immediately.
        async function beginExport(label, dest, startFn) {
            let checks = { inside_scanned: false, non_empty: false };
            try {
                checks = await pywebview.api.check_export_destination(dest);
            } catch (error) {
                console.error('Export destination check failed:', error);
            }

            const warnings = [];
            if (checks.inside_scanned) {
                warnings.push('This destination is inside a folder Felicity scans. Exported copies may be detected and added to the library on the next scan.');
            }
            if (checks.non_empty) {
                warnings.push('This destination is not empty. Existing files are kept; any new copy whose name clashes gets a _1, _2 suffix.');
            }

            if (warnings.length === 0) {
                startExportUI(label);
                await runExport(startFn);
                return;
            }

            pendingExport = { label, startFn };
            const body = document.getElementById('exportConfirmBody');
            body.innerHTML = '';
            warnings.forEach(text => {
                const line = document.createElement('div');
                line.className = 'export-result-line';
                line.textContent = text;
                body.appendChild(line);
            });
            document.getElementById('exportConfirmOverlay').classList.add('active');
        }

        async function runExport(startFn) {
            try {
                const res = await startFn();
                if (!res || !res.success) {
                    endExportUI();
                    showExportError(res ? res.message : 'Export failed to start');
                }
            } catch (error) {
                endExportUI();
                showExportError('Export failed to start: ' + error);
            }
        }

        async function cancelExport() {
            document.getElementById('exportCancelBtn').disabled = true;
            try {
                await pywebview.api.cancel_export();
            } catch (error) {
                console.error('Error cancelling export:', error);
            }
        }

        // Called from the backend (ExportWorker) when an export finishes.
        function showExportComplete(summary) {
            endExportUI();
            let title, lines;
            if (summary.error) {
                title = 'Export Failed';
                lines = [summary.error];
            } else if (summary.cancelled) {
                title = 'Export Cancelled';
                lines = [`${summary.exported} photos exported before cancelling`];
                if (summary.skipped_exists) lines.push(`${summary.skipped_exists} already present (skipped)`);
                if (summary.skipped_missing) lines.push(`${summary.skipped_missing} skipped (source missing)`);
                if (summary.failed) lines.push(`${summary.failed} failed`);
            } else if (summary.exported === 0 && summary.people === 0) {
                title = 'Nothing to Export';
                lines = ['No people with photos were found to export.'];
            } else {
                title = 'Export Complete';
                lines = [
                    `${summary.exported} photos exported`,
                    `${summary.people} ${summary.people === 1 ? 'person' : 'people'}`
                ];
                if (summary.skipped_exists) lines.push(`${summary.skipped_exists} already present (skipped)`);
                if (summary.skipped_missing) lines.push(`${summary.skipped_missing} skipped (source missing)`);
                if (summary.failed) lines.push(`${summary.failed} failed`);
            }
            showExportDialog(title, lines, summary.error ? null : summary.dest);
        }

        function showExportDialog(title, lines, dest) {
            document.getElementById('exportResultTitle').textContent = title;
            const body = document.getElementById('exportResultBody');
            body.innerHTML = '';
            lines.forEach(text => {
                const line = document.createElement('div');
                line.className = 'export-result-line';
                line.textContent = text;
                body.appendChild(line);
            });
            const openBtn = document.getElementById('exportOpenFolderBtn');
            if (dest) {
                openBtn.style.display = 'inline-flex';
                openBtn.onclick = () => pywebview.api.open_photo(dest);
            } else {
                openBtn.style.display = 'none';
            }
            document.getElementById('exportOverlay').classList.add('active');
        }

        function showExportError(message) {
            showExportDialog('Export Failed', [message], null);
        }

        document.getElementById('exportAllBtn').addEventListener('click', exportAllNamed);

        document.getElementById('exportCloseBtn').addEventListener('click', () => {
            document.getElementById('exportOverlay').classList.remove('active');
        });

        document.getElementById('exportOverlay').addEventListener('click', (e) => {
            if (e.target === document.getElementById('exportOverlay')) {
                document.getElementById('exportOverlay').classList.remove('active');
            }
        });

        document.getElementById('exportConfirmProceedBtn').addEventListener('click', async () => {
            document.getElementById('exportConfirmOverlay').classList.remove('active');
            if (pendingExport) {
                const { label, startFn } = pendingExport;
                pendingExport = null;
                startExportUI(label);
                await runExport(startFn);
            }
        });

        document.getElementById('exportConfirmCancelBtn').addEventListener('click', () => {
            document.getElementById('exportConfirmOverlay').classList.remove('active');
            pendingExport = null;
        });

        // Export Photos settings section: multi-select people list with search.
        let exportPeople = [];
        let exportSelected = new Set();

        async function loadExportPeople() {
            try {
                exportPeople = await pywebview.api.get_people_for_export();
            } catch (error) {
                console.error('Error loading people for export:', error);
                exportPeople = [];
            }
            // Drop any selections that no longer exist (visibility changed, recluster, etc.)
            const validIds = new Set(exportPeople.map(p => p.person_id));
            exportSelected.forEach(id => { if (!validIds.has(id)) exportSelected.delete(id); });
            renderExportPeople();
        }

        function renderExportPeople() {
            const container = document.getElementById('exportPeopleList');
            const filter = (document.getElementById('exportSearchInput').value || '').toLowerCase();
            const filtered = exportPeople.filter(p => p.name.toLowerCase().includes(filter));

            container.innerHTML = '';
            if (filtered.length === 0) {
                container.innerHTML = '<div style="color: #606060; padding: 12px; text-align: center; font-size: 13px;">No people available</div>';
                return;
            }

            filtered.forEach(p => {
                const item = document.createElement('div');
                item.className = 'folder-item export-person-item' + (exportSelected.has(p.person_id) ? ' selected' : '');
                item.textContent = p.name;
                item.addEventListener('click', () => {
                    if (exportSelected.has(p.person_id)) {
                        exportSelected.delete(p.person_id);
                        item.classList.remove('selected');
                    } else {
                        exportSelected.add(p.person_id);
                        item.classList.add('selected');
                    }
                });
                container.appendChild(item);
            });
        }

        document.getElementById('exportSearchInput').addEventListener('input', renderExportPeople);

        document.getElementById('exportSelectAllBtn').addEventListener('click', () => {
            const filter = (document.getElementById('exportSearchInput').value || '').toLowerCase();
            exportPeople
                .filter(p => p.name.toLowerCase().includes(filter))
                .forEach(p => exportSelected.add(p.person_id));
            renderExportPeople();
        });

        document.getElementById('exportClearBtn').addEventListener('click', () => {
            exportSelected.clear();
            renderExportPeople();
        });

        document.getElementById('exportSelectedBtn').addEventListener('click', async () => {
            if (exportSelected.size === 0) {
                showExportError('Select at least one person to export.');
                return;
            }
            const ids = Array.from(exportSelected);
            const dest = await pywebview.api.select_folder();
            if (!dest) return;
            const mode = getExportMode();
            const label = `Exporting ${ids.length} ${ids.length === 1 ? 'person' : 'people'}`;
            await beginExport(label, dest, () => pywebview.api.export_selected(ids, dest, mode));
        });

        let selectedIncludeFolder = null;
        let selectedExcludeFolder = null;
        let includeFolders = [];
        let excludeFolders = [];

        function renderIncludeFolders() {
            const container = document.getElementById('includeFolders');
            container.innerHTML = '';
            
            if (includeFolders.length === 0) {
                container.innerHTML = '<div style="color: #606060; padding: 12px; text-align: center; font-size: 13px;">No folders added yet</div>';
                return;
            }
            
            includeFolders.forEach((folder, index) => {
                const item = document.createElement('div');
                item.className = 'folder-item';
                item.setAttribute('data-path', folder);
                item.textContent = folder;
                
                item.addEventListener('click', () => {
                    document.querySelectorAll('#includeFolders .folder-item').forEach(el => {
                        el.classList.remove('selected');
                    });
                    item.classList.add('selected');
                    selectedIncludeFolder = index;
                });
                
                container.appendChild(item);
            });
        }

        function renderExcludeFolders() {
            const container = document.getElementById('excludeFolders');
            container.innerHTML = '';
            
            if (excludeFolders.length === 0) {
                container.innerHTML = '<div style="color: #606060; padding: 12px; text-align: center; font-size: 13px;">No folders excluded yet</div>';
                return;
            }
            
            excludeFolders.forEach((folder, index) => {
                const item = document.createElement('div');
                item.className = 'folder-item';
                item.setAttribute('data-path', folder);
                item.textContent = folder;
                
                item.addEventListener('click', () => {
                    document.querySelectorAll('#excludeFolders .folder-item').forEach(el => {
                        el.classList.remove('selected');
                    });
                    item.classList.add('selected');
                    selectedExcludeFolder = index;
                });
                
                container.appendChild(item);
            });
        }

        document.getElementById('addIncludeBtn').addEventListener('click', async () => {
            try {
                const folder = await pywebview.api.select_folder();
                if (folder) {
                    if (!includeFolders.includes(folder)) {
                        includeFolders.push(folder);
                        await pywebview.api.set_include_folders(includeFolders);
                        renderIncludeFolders();
                        addLogEntry('Added include folder: ' + folder);
                        closeNoFoldersOverlay();
                    } else {
                        addLogEntry('Folder already in list: ' + folder);
                    }
                }
            } catch (error) {
                console.error('Error selecting folder:', error);
                addLogEntry('Error selecting folder: ' + error);
            }
        });

        document.getElementById('removeIncludeBtn').addEventListener('click', async () => {
            if (selectedIncludeFolder !== null && selectedIncludeFolder < includeFolders.length) {
                const removed = includeFolders.splice(selectedIncludeFolder, 1)[0];
                selectedIncludeFolder = null;
                await pywebview.api.set_include_folders(includeFolders);
                renderIncludeFolders();
                addLogEntry('Removed include folder: ' + removed);
                checkNoFolders();
            } else {
                addLogEntry('No folder selected to remove');
            }
        });

        document.getElementById('addExcludeBtn').addEventListener('click', async () => {
            try {
                const folder = await pywebview.api.select_folder();
                if (folder) {
                    if (!excludeFolders.includes(folder)) {
                        excludeFolders.push(folder);
                        await pywebview.api.set_exclude_folders(excludeFolders);
                        renderExcludeFolders();
                        addLogEntry('Added exclude folder: ' + folder);
                    } else {
                        addLogEntry('Folder already in list: ' + folder);
                    }
                }
            } catch (error) {
                console.error('Error selecting folder:', error);
                addLogEntry('Error selecting folder: ' + error);
            }
        });

        document.getElementById('removeExcludeBtn').addEventListener('click', async () => {
            if (selectedExcludeFolder !== null && selectedExcludeFolder < excludeFolders.length) {
                const removed = excludeFolders.splice(selectedExcludeFolder, 1)[0];
                selectedExcludeFolder = null;
                await pywebview.api.set_exclude_folders(excludeFolders);
                renderExcludeFolders();
                addLogEntry('Removed exclude folder: ' + removed);
            } else {
                addLogEntry('No folder selected to remove');
            }
        });

        document.getElementById('wildcardInput').addEventListener('change', async (e) => {
            try {
                await pywebview.api.set_wildcard_exclusions(e.target.value);
                addLogEntry('Wildcard exclusions updated: ' + e.target.value);
            } catch (error) {
                console.error('Error saving wildcard exclusions:', error);
                addLogEntry('Error saving wildcard exclusions: ' + error);
            }
        });

        document.getElementById('rescanBtn').addEventListener('click', async () => {
            updateStatusMessage('Starting folder rescan...');
            setProgressVisible(true);
            closeSettings();
            
            try {
                await pywebview.api.start_scanning();
                addLogEntry('Manual rescan initiated');
            } catch (error) {
                console.error('Error starting rescan:', error);
                addLogEntry('Error starting rescan: ' + error);
            }
        });



        async function handleConflictProceed() {
            if (!nameConflictData) return;
            
            const savedData = { ...nameConflictData };
            
            closeNameConflictDialog();
            closeRenameDialog();
            
            try {
                const result = await pywebview.api.rename_person(
                    savedData.clusteringId,
                    savedData.personId,
                    savedData.originalName
                );
                
                if (result.success) {
                    addLogEntry(`Person renamed to "${savedData.originalName}" - ${result.faces_tagged} faces tagged`);
                    addLogEntry(`WARNING: This name already exists and will merge on next calibration`);
                    await loadPeople();
                } else {
                    addLogEntry('ERROR: ' + result.message);
                }
            } catch (error) {
                console.error('Error renaming person:', error);
                addLogEntry('Error renaming person: ' + error);
            }
        }


        async function handleConflictAutoRename() {
            if (!nameConflictData) return;
            
            const savedData = { ...nameConflictData };
            
            closeNameConflictDialog();
            closeRenameDialog();
            
            try {
                const result = await pywebview.api.rename_person(
                    savedData.clusteringId,
                    savedData.personId,
                    savedData.suggestedName
                );
                
                if (result.success) {
                    addLogEntry(`Person renamed to "${savedData.suggestedName}" - ${result.faces_tagged} faces tagged`);
                    await loadPeople();
                } else {
                    addLogEntry('ERROR: ' + result.message);
                }
            } catch (error) {
                console.error('Error renaming person:', error);
                addLogEntry('Error renaming person: ' + error);
            }
        }

        function handleConflictGoBack() {
            closeNameConflictDialog();
        }

        async function confirmRename() {
            if (!renameContext) return;
            
            const newName = document.getElementById('renameInput').value;
            
            if (!newName || newName.trim() === '') {
                addLogEntry('ERROR: Person name cannot be empty');
                closeRenameDialog();
                return;
            }
            
            const trimmedName = newName.trim();
            
            console.log('Attempting rename to:', trimmedName);
            console.log('For person:', renameContext.personId, 'in clustering:', renameContext.clusteringId);
            
            try {
                const conflictCheck = await pywebview.api.check_name_conflict(
                    renameContext.clusteringId,
                    renameContext.personId,
                    trimmedName
                );
                
                console.log('Conflict check result:', conflictCheck);
                
                if (conflictCheck.has_conflict) {
                    showNameConflictDialog(conflictCheck, trimmedName);
                    return;
                }
                
                const result = await pywebview.api.rename_person(
                    renameContext.clusteringId,
                    renameContext.personId,
                    trimmedName
                );
                
                console.log('Rename result:', result);
                
                if (result.success) {
                    addLogEntry(`Person renamed to "${trimmedName}" - ${result.faces_tagged} faces tagged`);
                    closeRenameDialog();
                    await loadPeople();
                } else {
                    addLogEntry('ERROR: ' + result.message);
                    closeRenameDialog();
                }
            } catch (error) {
                console.error('Error renaming person:', error);
                addLogEntry('Error renaming person: ' + error);
                closeRenameDialog();
            }
        }

        document.getElementById('renameConfirmBtn').addEventListener('click', confirmRename);
        document.getElementById('renameCancelBtn').addEventListener('click', closeRenameDialog);

        document.getElementById('renameOverlay').addEventListener('click', (e) => {
            if (e.target === document.getElementById('renameOverlay')) {
                closeRenameDialog();
            }
        });

        document.getElementById('renameInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                confirmRename();
            } else if (e.key === 'Escape') {
                closeRenameDialog();
            }
        });

        async function renamePerson(clusteringId, personId, currentName) {
            closeAllMenus();
            showRenameDialog(clusteringId, personId, currentName);
        }

        async function untagPerson(clusteringId, personId) {
            closeAllMenus();
            
            if (!confirm('Remove all tags from this person? They will revert to "Person X" until renamed again.')) {
                return;
            }
            
            try {
                const result = await pywebview.api.untag_person(clusteringId, personId);
                if (result.success) {
                    addLogEntry(`Removed all tags from person ${personId} - ${result.faces_untagged} faces untagged`);
                } else {
                    addLogEntry('ERROR: ' + result.message);
                }
            } catch (error) {
                console.error('Error untagging person:', error);
                addLogEntry('Error untagging person: ' + error);
            }
        }

        async function hidePerson(clusteringId, personId) {
            try {
                await pywebview.api.hide_person(clusteringId, personId);
                addLogEntry('Person hidden: ' + personId);
                closeAllMenus();
            } catch (error) {
                console.error('Error hiding person:', error);
                addLogEntry('Error hiding person: ' + error);
            }
        }

        async function unhidePerson(clusteringId, personId) {
            try {
                await pywebview.api.unhide_person(clusteringId, personId);
                addLogEntry('Person unhidden: ' + personId);
                closeAllMenus();
            } catch (error) {
                console.error('Error unhiding person:', error);
                addLogEntry('Error unhiding person: ' + error);
            }
        }

        async function makePrimaryPhoto() {
            closeAllMenus();
            
            if (!currentPhotoContext) {
                addLogEntry('ERROR: No photo context available');
                return;
            }
            
            const cleanName = currentPhotoContext.person_name.replace(' (hidden)', '');
            const faceId = currentPhotoContext.face_id;
            
            try {
                const result = await pywebview.api.set_primary_photo(cleanName, faceId);
                
                if (result.success) {
                    addLogEntry(`Primary photo set for ${cleanName}`);
                } else {
                    addLogEntry('ERROR: ' + result.message);
                }
            } catch (error) {
                console.error('Error setting primary photo:', error);
                addLogEntry('Error setting primary photo: ' + error);
            }
        }

        // Map representative face ids (what selection and menus carry) to every face
        // id in their deduped group, so hide and tag-transfer act on the whole photo
        // for this person - not just the single shown face (F3). Other people's faces
        // in the same file are untouched, so the photo still shows for them.
        function collectGroupFaceIds(repFaceIds) {
            const byRep = new Map();
            for (const p of lightboxPhotos) byRep.set(p.face_id, p.face_ids || [p.face_id]);
            const out = [];
            const seen = new Set();
            for (const rep of repFaceIds) {
                for (const id of (byRep.get(rep) || [rep])) {
                    if (!seen.has(id)) { seen.add(id); out.push(id); }
                }
            }
            return out;
        }

        async function hidePhotos() {
            closeAllMenus();

            const faceIds = selectedPhotos.size > 0 ? Array.from(selectedPhotos) : [currentPhotoContext.face_id];
            const groupIds = collectGroupFaceIds(faceIds);

            try {
                for (const faceId of groupIds) {
                    await pywebview.api.hide_photo(faceId);
                }
                addLogEntry(`${faceIds.length} photo(s) hidden`);
                clearSelection();
            } catch (error) {
                console.error('Error hiding photos:', error);
                addLogEntry('Error hiding photos: ' + error);
            }
        }

        async function unhidePhotos() {
            closeAllMenus();

            const faceIds = selectedPhotos.size > 0 ? Array.from(selectedPhotos) : [currentPhotoContext.face_id];
            const groupIds = collectGroupFaceIds(faceIds);

            try {
                for (const faceId of groupIds) {
                    await pywebview.api.unhide_photo(faceId);
                }
                addLogEntry(`${faceIds.length} photo(s) unhidden`);
                clearSelection();
            } catch (error) {
                console.error('Error unhiding photos:', error);
                addLogEntry('Error unhiding photos: ' + error);
            }
        }

        function closeAllMenus() {
            document.querySelectorAll('.context-menu').forEach(m => {
                m.classList.remove('show');
            });
            document.querySelectorAll('.person-item, .photo-item').forEach(item => {
                item.classList.remove('menu-active');
            });
            activeMenu = null;
        }

        document.addEventListener('click', (e) => {
            if (!e.target.closest('.kebab-menu') && !e.target.closest('.context-menu') && !e.target.closest('#filterBtn')) {
                if (selectedPhotos.size === 0) {
                    closeAllMenus();
                }
            }
        });

        document.querySelectorAll('.info-icon').forEach(icon => {
            icon.addEventListener('mouseenter', function(e) {
                if (!this.classList.contains('info-icon')) return;
                
                const tooltip = this.querySelector('.tooltip');
                if (!tooltip) return;
                
                const iconRect = this.getBoundingClientRect();
                const tooltipWidth = 320;
                
                let left = iconRect.left + (iconRect.width / 2) - (tooltipWidth / 2);
                let top = iconRect.top - 12;
                
                if (left < 10) left = 10;
                if (left + tooltipWidth > window.innerWidth - 10) {
                    left = window.innerWidth - tooltipWidth - 10;
                }
                
                tooltip.style.left = left + 'px';
                tooltip.style.top = top + 'px';
                tooltip.style.transform = 'translateY(-100%)';
            });
        });

        // Suppress the native browser menu everywhere. Right-clicks on a person row or
        // a photo cell are handled by their own listeners (which stopPropagation), so
        // this only runs for empty/other areas - where it also closes any open menu.
        document.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            closeAllMenus();
        });

        document.getElementById('conflictProceedBtn').addEventListener('click', handleConflictProceed);
        document.getElementById('conflictAutoRenameBtn').addEventListener('click', handleConflictAutoRename);
        document.getElementById('conflictGoBackBtn').addEventListener('click', handleConflictGoBack);

        document.getElementById('nameConflictOverlay').addEventListener('click', (e) => {
            if (e.target === document.getElementById('nameConflictOverlay')) {
                handleConflictGoBack();
            }
        });
        document.getElementById('minimizeBtn').addEventListener('click', () => {
            pywebview.api.minimize_window();
        });

        document.getElementById('maximizeBtn').addEventListener('click', () => {
            pywebview.api.maximize_window();
        });

        document.getElementById('closeBtn').addEventListener('click', () => {
            pywebview.api.close_window();
        });

        function showCleanupMessage() {
            document.getElementById('cleanupOverlay').classList.add('active');
            document.getElementById('appContainer').classList.add('blurred');
        }

        window.addEventListener('pywebviewready', initialize);