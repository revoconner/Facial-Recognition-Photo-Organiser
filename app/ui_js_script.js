let people = [];
        let currentPerson = null;
        let isAlphabetMode = false;
        let activeMenu = null;
        let showUnmatched = false;
        let showHidden = false;
        let showHiddenPhotos = false;
        let showDevOptions = false;
        let currentPhotoContext = null;
        let currentSortMode = 'names_asc';
        let menuCloseTimeout = null;
        const personColors = [
            '#667eea', '#f093fb', '#4facfe', '#43e97b', '#fa709a',
            '#30cfd0', '#a8edea', '#fed6e3', '#c1dfc4', '#d299c2',
            '#fda085', '#f6d365', '#96e6a1', '#764ba2', '#f79d00'
        ];

        function getPersonColor(personId) {
            return personColors[personId % personColors.length];
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
            
            await loadPhotos(person.clustering_id, person.id);
        }

        async function loadPhotos(clustering_id, person_id) {
            const photoGrid = document.getElementById('photoGrid');
            photoGrid.innerHTML = '<div style="color: #a0a0a0; padding: 20px;">Loading photos...</div>';
            
            try {
                const photos = await pywebview.api.get_photos(clustering_id, person_id);
                photoGrid.innerHTML = '';
                
                if (photos.length === 0) {
                    photoGrid.innerHTML = '<div style="color: #a0a0a0; padding: 20px;">No photos found</div>';
                    return;
                }
                
                photos.forEach(photo => {
                    const photoItem = document.createElement('div');
                    photoItem.className = 'photo-item';
                    photoItem.setAttribute('data-face-id', photo.face_id);
                    
                    const opacityStyle = photo.is_hidden ? 'opacity: 0.5; filter: grayscale(100%);' : '';
                    
                    photoItem.innerHTML = `
                        <img src="${photo.thumbnail}" class="photo-placeholder" style="width: 100%; height: 100%; object-fit: cover; ${opacityStyle}">
                        <button class="kebab-menu">
                            <span class="kebab-dot"></span>
                            <span class="kebab-dot"></span>
                            <span class="kebab-dot"></span>
                        </button>
                    `;
                    
                    const contextMenu = document.createElement('div');
                    contextMenu.className = 'context-menu';
                    
                    if (photo.is_hidden) {
                        contextMenu.innerHTML = `
                            <div class="context-menu-item" data-action="make-primary">Make primary photo</div>
                            <div class="context-menu-item" data-action="unhide-photo">Unhide photo</div>
                        `;
                    } else {
                        contextMenu.innerHTML = `
                            <div class="context-menu-item" data-action="make-primary">Make primary photo</div>
                            <div class="context-menu-item" data-action="hide-photo">Hide photo</div>
                        `;
                    }
                    
                    document.body.appendChild(contextMenu);
                    
                    photoItem.addEventListener('dblclick', () => {
                        pywebview.api.open_photo(photo.path);
                    });
                    
                    photoGrid.appendChild(photoItem);

                    const kebabBtn = photoItem.querySelector('.kebab-menu');
                    kebabBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        closeAllMenus();
                        
                        currentPhotoContext = {
                            person_name: currentPerson.name,
                            face_id: photo.face_id,
                            path: photo.path,
                            is_hidden: photo.is_hidden
                        };
                        
                        contextMenu.classList.add('show');
                        photoItem.classList.add('menu-active');
                        activeMenu = { element: contextMenu, parent: photoItem };
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

                    contextMenu.addEventListener('click', (e) => {
                        const menuItem = e.target.closest('.context-menu-item');
                        if (menuItem) {
                            const action = menuItem.getAttribute('data-action');
                            if (action === 'make-primary') {
                                makePrimaryPhoto();
                            } else if (action === 'hide-photo') {
                                hidePhoto();
                            } else if (action === 'unhide-photo') {
                                unhidePhoto();
                            }
                        }
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
            } catch (error) {
                console.error('Error loading photos:', error);
                photoGrid.innerHTML = '<div style="color: #ff6b6b; padding: 20px;">Error loading photos</div>';
            }
        }

        async function reloadCurrentPhotos() {
            if (currentPerson) {
                await loadPhotos(currentPerson.clustering_id, currentPerson.id);
            }
        }

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
                
                addLogEntry('Settings loaded successfully');
            } catch (error) {
                console.error('Error loading settings:', error);
                addLogEntry('ERROR: Failed to load settings - ' + error);
            }
        }

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
                
                document.getElementById('progressSection').style.display = 'flex';
                
                const state = await pywebview.api.check_initial_state();
                
                updateStatusMessage('Checking for new photos...');
            } catch (error) {
                console.error('Initialization error:', error);
                addLogEntry('ERROR: Initialization failed - ' + error);
            }
        }

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

        document.getElementById('sizeSlider').addEventListener('input', (e) => {
            const size = e.target.value;
            document.getElementById('photoGrid').style.gridTemplateColumns = 
                `repeat(auto-fill, minmax(${size}px, 1fr))`;
            pywebview.api.set_grid_size(parseInt(size));
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

        async function renamePerson(clusteringId, personId, currentName) {
            closeAllMenus();
            
            const cleanName = currentName.replace(' (hidden)', '');
            
            const newName = prompt('Enter new name for this person:', cleanName);
            
            if (newName === null) {
                return;
            }
            
            if (newName.trim() === '') {
                addLogEntry('ERROR: Person name cannot be empty');
                alert('Name cannot be empty');
                return;
            }
            
            try {
                const result = await pywebview.api.rename_person(clusteringId, personId, newName.trim());
                if (result.success) {
                    addLogEntry(`Person renamed to "${newName.trim()}" - ${result.faces_tagged} faces tagged`);
                } else {
                    addLogEntry('ERROR: ' + result.message);
                    alert('Error: ' + result.message);
                }
            } catch (error) {
                console.error('Error renaming person:', error);
                addLogEntry('Error renaming person: ' + error);
                alert('Error renaming person');
            }
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
            
            try {
                const result = await pywebview.api.set_primary_photo(
                    cleanName,
                    currentPhotoContext.face_id
                );
                
                if (result.success) {
                    addLogEntry(`Primary photo set for ${cleanName}`);
                } else {
                    addLogEntry('ERROR: ' + result.message);
                    alert(result.message);
                }
            } catch (error) {
                console.error('Error setting primary photo:', error);
                addLogEntry('Error setting primary photo: ' + error);
                alert('Error setting primary photo');
            }
            
            currentPhotoContext = null;
        }

        async function hidePhoto() {
            closeAllMenus();
            
            if (!currentPhotoContext) {
                addLogEntry('ERROR: No photo context available');
                return;
            }
            
            try {
                const result = await pywebview.api.hide_photo(currentPhotoContext.face_id);
                if (result.success) {
                    addLogEntry(`Photo hidden: face_id ${currentPhotoContext.face_id}`);
                }
            } catch (error) {
                console.error('Error hiding photo:', error);
                addLogEntry('Error hiding photo: ' + error);
            }
            
            currentPhotoContext = null;
        }

        async function unhidePhoto() {
            closeAllMenus();
            
            if (!currentPhotoContext) {
                addLogEntry('ERROR: No photo context available');
                return;
            }
            
            try {
                const result = await pywebview.api.unhide_photo(currentPhotoContext.face_id);
                if (result.success) {
                    addLogEntry(`Photo unhidden: face_id ${currentPhotoContext.face_id}`);
                }
            } catch (error) {
                console.error('Error unhiding photo:', error);
                addLogEntry('Error unhiding photo: ' + error);
            }
            
            currentPhotoContext = null;
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
                closeAllMenus();
            }
        });

        document.querySelectorAll('.info-icon').forEach(icon => {
            icon.addEventListener('mouseenter', function() {
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
