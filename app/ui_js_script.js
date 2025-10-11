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
        let menuCloseTimeout = null;
        let renameContext = null;
        let lightboxPhotos = [];
        let lightboxCurrentIndex = 0;
        let transferContext = null;
        let currentPage = 1;
        const PAGE_SIZE = 100;
        let isLoadingMore = false;
        let hasMorePhotos = true;
        let scrollCheckInterval = null;
        let hideUnnamedPersons = false;
        let selectedPhotos = new Set();
        let lastSelectedIndex = -1;
        let nameConflictData = null;
        let virtualGrid = null;
        let showFaceTagsPreview = true;

        const personColors = [
            '#667eea', '#f093fb', '#4facfe', '#43e97b', '#fa709a',
            '#30cfd0', '#a8edea', '#fed6e3', '#c1dfc4', '#d299c2',
            '#fda085', '#f6d365', '#96e6a1', '#764ba2', '#f79d00'
        ];

        function initVirtualGrid() {
            const container = document.querySelector('.photo-grid-container');
            const gridSize = parseInt(document.getElementById('sizeSlider').value) || 180;
            const containerWidth = container.clientWidth - 56;
            
            if (virtualGrid) {
                virtualGrid.destroy();
            }
            
            virtualGrid = new VirtualPhotoGrid(container, {
                itemHeight: gridSize,
                itemsPerRow: Math.max(1, Math.floor(containerWidth / (gridSize + 16))),
                gap: 16,
                overscan: 2
            });
        }


        document.getElementById('sizeSlider').addEventListener('input', (e) => {
            const size = parseInt(e.target.value);
            pywebview.api.set_grid_size(size);
            
            if (virtualGrid && lightboxPhotos.length > 0) {
                const containerWidth = virtualGrid.container.clientWidth - 56;
                const newItemsPerRow = Math.max(1, Math.floor(containerWidth / (size + 16)));
                
                virtualGrid.itemHeight = size;
                virtualGrid.itemsPerRow = newItemsPerRow;
                
                for (const [index] of virtualGrid.visibleItems.entries()) {
                    virtualGrid.updatePhotoPosition(index);
                }
                
                virtualGrid.updateLayout();
            }
        });


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
            const start = Math.min(startIndex, endIndex);
            const end = Math.max(startIndex, endIndex);
            
            for (let i = start; i <= end && i < lightboxPhotos.length; i++) {
                const photo = lightboxPhotos[i];
                selectedPhotos.add(photo.face_id);
            }
            
            if (virtualGrid) {
                virtualGrid.updateSelections();
            }
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
            
            return sorted;
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
            
            sortedPeople.forEach(person => {
                const item = document.createElement('div');
                item.className = 'person-item';
                if (currentPerson && person.id === currentPerson.id) {
                    item.classList.add('active');
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
                
                item.innerHTML = `
                    ${avatarHTML}
                    <div class="person-info">
                        <div class="person-name">${person.name}</div>
                        <div class="person-count">${person.count} photos${tagInfo}</div>
                    </div>
                    <button class="kebab-menu">
                        <span class="kebab-dot"></span>
                        <span class="kebab-dot"></span>
                        <span class="kebab-dot"></span>
                    </button>
                `;
                
                const contextMenu = document.createElement('div');
                contextMenu.className = 'context-menu';
                
                let menuHTML = '';
                
                if (person.is_hidden) {
                    menuHTML = `<div class="context-menu-item" onclick="renamePerson(${person.clustering_id}, ${person.id}, '${person.name.replace(/'/g, "\\'")}')">Rename</div>`;
                    if (showDevOptions) {
                        menuHTML += `<div class="context-menu-item" onclick="untagPerson(${person.clustering_id}, ${person.id})">Remove all tags</div>`;
                    }
                    menuHTML += `<div class="context-menu-item" onclick="unhidePerson(${person.clustering_id}, ${person.id})">Unhide person</div>`;
                } else {
                    menuHTML = `<div class="context-menu-item" onclick="renamePerson(${person.clustering_id}, ${person.id}, '${person.name.replace(/'/g, "\\'")}')">Rename</div>`;
                    if (showDevOptions) {
                        menuHTML += `<div class="context-menu-item" onclick="untagPerson(${person.clustering_id}, ${person.id})">Remove all tags</div>`;
                    }
                    menuHTML += `<div class="context-menu-item" onclick="hidePerson(${person.clustering_id}, ${person.id})">Hide person</div>`;
                }
                
                contextMenu.innerHTML = menuHTML;
                
                document.body.appendChild(contextMenu);
                
                item.addEventListener('click', (e) => {
                    if (!e.target.closest('.kebab-menu') && !e.target.closest('.context-menu')) {
                        selectPerson(person);
                    }
                });
                
                peopleList.appendChild(item);

                const kebabBtn = item.querySelector('.kebab-menu');
                kebabBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const personItem = kebabBtn.closest('.person-item');
                    
                    closeAllMenus();
                    
                    contextMenu.classList.add('show');
                    personItem.classList.add('menu-active');
                    activeMenu = { element: contextMenu, parent: personItem };
                    
                    positionMenu(contextMenu, kebabBtn);
                });

                kebabBtn.addEventListener('mouseenter', () => {
                    if (menuCloseTimeout) {
                        clearTimeout(menuCloseTimeout);
                        menuCloseTimeout = null;
                    }
                });

                kebabBtn.addEventListener('mouseleave', () => {
                    menuCloseTimeout = setTimeout(() => {
                        closeAllMenus();
                    }, 200);
                });

                contextMenu.addEventListener('mouseenter', () => {
                    if (menuCloseTimeout) {
                        clearTimeout(menuCloseTimeout);
                        menuCloseTimeout = null;
                    }
                });

                contextMenu.addEventListener('mouseleave', () => {
                    menuCloseTimeout = setTimeout(() => {
                        closeAllMenus();
                    }, 200);
                });
            });
        }

        async function selectPerson(person) {
            currentPerson = person;
            lightboxPhotos = [];
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
            
            await loadPhotos(person.clustering_id, person.id, true);
        }

        async function loadPhotos(clustering_id, person_id, resetGrid = false) {
            if (!virtualGrid) {
                initVirtualGrid();
            }
            
            if (resetGrid) {
                lightboxPhotos = [];
                clearSelection();
                virtualGrid.setPhotos([]);
            }
            
            try {
                const result = await pywebview.api.get_photos(clustering_id, person_id, 1, 999999);
                
                if (!result || typeof result !== 'object') {
                    throw new Error('Invalid response from get_photos');
                }
                
                lightboxPhotos = result.photos || [];
                virtualGrid.setPhotos(lightboxPhotos);
                
            } catch (error) {
                console.error('Error loading photos:', error);
                addLogEntry('ERROR loading photos: ' + error.toString());
            }
        }

        async function reloadCurrentPhotos() {
            if (currentPerson) {
                await loadPhotos(currentPerson.clustering_id, currentPerson.id, true);
            }
        }

        
        function openLightbox(index) {
            lightboxCurrentIndex = index;
            updateLightbox();
            document.getElementById('lightboxOverlay').classList.add('active');
            document.getElementById('appContainer').classList.add('blurred');
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
            const contentRect = document.getElementById('lightboxContent').getBoundingClientRect();
            
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

        async function updateLightbox() {
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
                        lightboxImage.src = photo.thumbnail;
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
                        lightboxImage.src = photo.thumbnail;
                    }
                    lightboxImage.onload = null;
                }
            } catch (error) {
                console.error('Error loading full size preview:', error);
                document.getElementById('lightboxImage').src = photo.thumbnail;
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
            
            transferContext = {
                face_ids: faceIds,
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

        function updateStatusMessage(message) {
            document.getElementById('progressText').textContent = message;
            addLogEntry(message);
        }

        function updateProgress(current, total, percent) {
            document.getElementById('progressFill').style.width = percent + '%';
            document.getElementById('progressText').textContent = `Scanning: ${current}/${total}`;
        }

        function hideProgress() {
            document.getElementById('progressSection').style.display = 'none';
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

        function addLogEntry(message) {
            const logViewer = document.getElementById('logViewer');
            const now = new Date();
            const timestamp = now.toLocaleString();
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.textContent = `[${timestamp}] ${message}`;
            logViewer.appendChild(entry);
            logViewer.scrollTop = logViewer.scrollHeight;
        }



        async function loadAllSettings() {
            try {
                const threshold = await pywebview.api.get_threshold();
                document.getElementById('thresholdSlider').value = threshold;
                document.getElementById('thresholdValue').textContent = threshold + '%';
                
                const scanFrequency = await pywebview.api.get_scan_frequency();
                document.getElementById('scanFrequencyDropdown').value = scanFrequency;
                
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
                
                const gridSize = await pywebview.api.get_grid_size();
                document.getElementById('sizeSlider').value = gridSize;
                document.getElementById('photoGrid').style.gridTemplateColumns = 
                    `repeat(auto-fill, minmax(${gridSize}px, 1fr))`;
                
                const viewMode = await pywebview.api.get_view_mode();
                document.getElementById('viewModeDropdown').value = viewMode;
                
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

        function checkScrollPosition() {
            if (!currentPerson || !hasMorePhotos || isLoadingMore) {
                return;
            }
            
            const photoGridContainer = document.querySelector('.photo-grid-container');
            if (!photoGridContainer) return;
            
            const scrollTop = photoGridContainer.scrollTop;
            const scrollHeight = photoGridContainer.scrollHeight;
            const clientHeight = photoGridContainer.clientHeight;
            
            const distanceFromBottom = scrollHeight - (scrollTop + clientHeight);
            
            if (distanceFromBottom < 800) {
                console.log(`Triggering load: ${distanceFromBottom}px from bottom`);
                loadPhotos(currentPerson.clustering_id, currentPerson.id, false);
            }
        }

        const photoGridContainer = document.querySelector('.photo-grid-container');
        if (photoGridContainer) {
            let scrollTimeout = null;
            
            photoGridContainer.addEventListener('scroll', () => {
                if (scrollTimeout) {
                    clearTimeout(scrollTimeout);
                }
                
                scrollTimeout = setTimeout(() => {
                    checkScrollPosition();
                }, 100);
            });
            
            if (scrollCheckInterval) {
                clearInterval(scrollCheckInterval);
            }
            
            scrollCheckInterval = setInterval(() => {
                if (currentPerson && hasMorePhotos && !isLoadingMore) {
                    checkScrollPosition();
                }
            }, 500);
        }

        async function initialize() {
            try {
                addLogEntry('Application started');
                
                const sysInfo = await pywebview.api.get_system_info();
                document.getElementById('pytorchVersion').textContent = `PyTorch ${sysInfo.pytorch_version}`;
                document.getElementById('gpuStatus').textContent = sysInfo.gpu_available ? 'GPU Available' : 'CPU Only';
                document.getElementById('cudaVersion').textContent = `CUDA: ${sysInfo.cuda_version}`;
                document.getElementById('faceCount').textContent = `Found: ${sysInfo.total_faces} faces`;
                
                addLogEntry(`System: PyTorch ${sysInfo.pytorch_version}, ${sysInfo.gpu_available ? 'GPU' : 'CPU'}, CUDA ${sysInfo.cuda_version}`);
                
                await loadAllSettings();
                
                initVirtualGrid();
                
                document.getElementById('progressSection').style.display = 'flex';
                
                const state = await pywebview.api.check_initial_state();
                
                updateStatusMessage('Checking for new photos...');
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
            
            filterMenu.addEventListener('mouseenter', () => {
                if (menuCloseTimeout) {
                    clearTimeout(menuCloseTimeout);
                    menuCloseTimeout = null;
                }
            });
            
            filterMenu.addEventListener('mouseleave', () => {
                menuCloseTimeout = setTimeout(() => {
                    closeAllMenus();
                }, 200);
            });
        });

        document.getElementById('filterBtn').addEventListener('mouseenter', () => {
            if (menuCloseTimeout) {
                clearTimeout(menuCloseTimeout);
                menuCloseTimeout = null;
            }
        });

        document.getElementById('filterBtn').addEventListener('mouseleave', () => {
            menuCloseTimeout = setTimeout(() => {
                closeAllMenus();
            }, 200);
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


        document.getElementById('viewModeDropdown').addEventListener('change', async (e) => {
            const mode = e.target.value;
            try {
                await pywebview.api.set_view_mode(mode);
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
            });
        });

        thresholdSlider.addEventListener('input', (e) => {
            thresholdValue.textContent = e.target.value + '%';
            pywebview.api.set_threshold(parseInt(e.target.value));
        });

        document.getElementById('recalibrateBtn').addEventListener('click', async () => {
            const threshold = parseInt(thresholdSlider.value);
            updateStatusMessage('Starting recalibration...');
            document.getElementById('progressSection').style.display = 'flex';
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
            document.getElementById('progressSection').style.display = 'flex';
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

        async function hidePhotos() {
            closeAllMenus();
            
            const faceIds = selectedPhotos.size > 0 ? Array.from(selectedPhotos) : [currentPhotoContext.face_id];
            
            try {
                for (const faceId of faceIds) {
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
            
            try {
                for (const faceId of faceIds) {
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
            if (menuCloseTimeout) {
                clearTimeout(menuCloseTimeout);
                menuCloseTimeout = null;
            }
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

        document.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            return false;
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