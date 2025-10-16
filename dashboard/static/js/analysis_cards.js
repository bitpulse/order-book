// Analysis Cards Grid - Main landing page for Price Change Analyzer

let currentDeleteId = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadAnalysisCards();
    setupEventListeners();
});

// Load and render analysis cards
async function loadAnalysisCards() {
    const loading = document.getElementById('loading');
    const zeroState = document.getElementById('zero-state');
    const cardsGrid = document.getElementById('cards-grid');

    // Show loading
    loading.style.display = 'flex';
    zeroState.style.display = 'none';
    cardsGrid.innerHTML = '';

    try {
        const response = await fetch('/api/files');
        const data = await response.json();

        loading.style.display = 'none';

        if (!data.files || data.files.length === 0) {
            // Show zero state
            zeroState.style.display = 'flex';
            return;
        }

        // Render cards
        data.files.forEach(file => {
            const card = createAnalysisCard(file);
            cardsGrid.appendChild(card);
        });

    } catch (error) {
        console.error('Error loading analyses:', error);
        loading.style.display = 'none';
        showError('Failed to load analyses: ' + error.message);
    }
}

// Create analysis card element
function createAnalysisCard(file) {
    const card = document.createElement('div');
    card.className = 'analysis-card';
    card.dataset.id = file.id;

    // Determine card type based on top change (fetch from stats if available)
    // For now, we'll use neutral as we don't have the data yet
    // In the future, we could fetch this from the API
    card.classList.add('neutral');

    const createdDate = file.created_at ? new Date(file.created_at) : new Date();
    const formattedCreatedTime = createdDate.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });

    // Format from/to times if available
    let fromTimeFormatted = 'Loading...';
    let toTimeFormatted = 'Loading...';

    if (file.from_time) {
        const fromDate = new Date(file.from_time);
        fromTimeFormatted = fromDate.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    if (file.to_time) {
        const toDate = new Date(file.to_time);
        toTimeFormatted = toDate.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    card.innerHTML = `
        <div class="card-header">
            <div class="card-symbol">${file.symbol || 'Unknown'}</div>
            <button class="card-delete-btn" data-id="${file.id}" title="Delete analysis">
                🗑️
            </button>
        </div>
        <div class="card-stats">
            <div class="card-stat-row">
                <span class="card-stat-label">From</span>
                <span class="card-stat-value">${fromTimeFormatted}</span>
            </div>
            <div class="card-stat-row">
                <span class="card-stat-label">To</span>
                <span class="card-stat-value">${toTimeFormatted}</span>
            </div>
            <div class="card-stat-row">
                <span class="card-stat-label">Created</span>
                <span class="card-stat-value">${formattedCreatedTime}</span>
            </div>
        </div>
        <div class="card-change neutral" data-id="${file.id}">
            <div class="spinner" style="width: 24px; height: 24px; margin: 0 auto;"></div>
        </div>
        <div class="card-footer">
            <span class="card-timestamp">${file.id.substring(0, 12)}...</span>
            <span class="card-intervals-badge" data-id="${file.id}">Loading...</span>
        </div>
    `;

    // Add click handler to navigate to detail page (not on delete button)
    card.addEventListener('click', (e) => {
        if (!e.target.closest('.card-delete-btn')) {
            window.location.href = `/analysis/${file.id}`;
        }
    });

    // Add delete button handler
    const deleteBtn = card.querySelector('.card-delete-btn');
    deleteBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        showDeleteConfirmation(file.id);
    });

    // Load card stats asynchronously
    loadCardStats(file.id);

    return card;
}

// Load card statistics from API
async function loadCardStats(analysisId) {
    try {
        const response = await fetch(`/api/data/${analysisId}`);
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        // Extract stats
        let topChange = 0;
        let intervalCount = 0;

        if (Array.isArray(data)) {
            // Legacy format
            intervalCount = data.length;
            if (data.length > 0) {
                topChange = data[0].change_pct;
            }
        } else if (data.intervals) {
            // New format
            intervalCount = data.intervals.length;
            if (data.intervals.length > 0) {
                topChange = data.intervals[0].change_pct;
            }
        }

        // Update card
        const card = document.querySelector(`.analysis-card[data-id="${analysisId}"]`);
        if (!card) return;

        // Update change display
        const changeEl = card.querySelector('.card-change');
        changeEl.textContent = `${topChange >= 0 ? '+' : ''}${topChange.toFixed(3)}%`;
        changeEl.classList.remove('neutral');
        changeEl.classList.add(topChange >= 0 ? 'positive' : 'negative');

        // Update card border
        card.classList.remove('neutral');
        card.classList.add(topChange >= 0 ? 'positive' : 'negative');

        // Update interval count
        const intervalBadge = card.querySelector('.card-intervals-badge');
        intervalBadge.textContent = `${intervalCount} intervals`;

    } catch (error) {
        console.error(`Error loading stats for ${analysisId}:`, error);

        // Show error state
        const card = document.querySelector(`.analysis-card[data-id="${analysisId}"]`);
        if (card) {
            const changeEl = card.querySelector('.card-change');
            changeEl.innerHTML = '<span style="font-size: 0.9rem; color: var(--red);">Error loading</span>';

            const intervalBadge = card.querySelector('.card-intervals-badge');
            intervalBadge.textContent = 'N/A';
        }
    }
}

// Setup event listeners
function setupEventListeners() {
    // New analysis button
    document.getElementById('new-analysis-btn').addEventListener('click', () => {
        document.getElementById('new-analysis-modal').style.display = 'flex';
    });

    // Zero state new analysis button
    const zeroStateBtn = document.getElementById('zero-state-new-analysis');
    if (zeroStateBtn) {
        zeroStateBtn.addEventListener('click', () => {
            document.getElementById('new-analysis-modal').style.display = 'flex';
        });
    }

    // Refresh button
    document.getElementById('refresh-btn').addEventListener('click', async () => {
        await loadAnalysisCards();
    });

    // Analysis form submit
    document.getElementById('analysis-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        await runAnalysis();
    });

    // Confirm delete button
    document.getElementById('confirm-delete-btn').addEventListener('click', async () => {
        if (currentDeleteId) {
            await deleteAnalysis(currentDeleteId);
        }
    });

    // Close modal on background click
    document.getElementById('new-analysis-modal').addEventListener('click', (e) => {
        if (e.target.id === 'new-analysis-modal') {
            e.target.style.display = 'none';
        }
    });

    document.getElementById('delete-modal').addEventListener('click', (e) => {
        if (e.target.id === 'delete-modal') {
            e.target.style.display = 'none';
        }
    });
}

// Show delete confirmation modal
function showDeleteConfirmation(analysisId) {
    currentDeleteId = analysisId;
    document.getElementById('delete-modal').style.display = 'flex';
}

// Delete analysis
async function deleteAnalysis(analysisId) {
    const confirmBtn = document.getElementById('confirm-delete-btn');
    const originalText = confirmBtn.textContent;

    try {
        // Show loading state
        confirmBtn.textContent = 'Deleting...';
        confirmBtn.disabled = true;

        const response = await fetch(`/api/delete/${analysisId}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (response.ok && result.success) {
            // Close modal
            document.getElementById('delete-modal').style.display = 'none';
            currentDeleteId = null;

            // Remove card from UI
            const card = document.querySelector(`.analysis-card[data-id="${analysisId}"]`);
            if (card) {
                card.style.transition = 'all 0.3s ease';
                card.style.transform = 'scale(0)';
                card.style.opacity = '0';

                setTimeout(() => {
                    card.remove();

                    // Check if grid is empty
                    const cardsGrid = document.getElementById('cards-grid');
                    if (cardsGrid.children.length === 0) {
                        document.getElementById('zero-state').style.display = 'flex';
                    }
                }, 300);
            }

            console.log('Analysis deleted successfully');
        } else {
            throw new Error(result.error || 'Failed to delete analysis');
        }
    } catch (error) {
        console.error('Delete error:', error);
        showError('Failed to delete analysis: ' + error.message);
    } finally {
        // Reset button state
        confirmBtn.textContent = originalText;
        confirmBtn.disabled = false;
    }
}

// Run new analysis
async function runAnalysis() {
    const form = document.getElementById('analysis-form');
    const statusDiv = document.getElementById('analysis-status');
    const statusMsg = document.getElementById('status-message');

    // Get form values
    const params = {
        symbol: document.getElementById('symbol-input').value,
        lookback: document.getElementById('lookback-input').value,
        interval: document.getElementById('interval-input').value,
        top: parseInt(document.getElementById('top-input').value),
        min_change: parseFloat(document.getElementById('min-change-input').value)
    };

    // Show status
    form.style.display = 'none';
    statusDiv.style.display = 'flex';
    statusMsg.textContent = `Running analysis for ${params.symbol}...`;

    try {
        const response = await fetch('/api/run-analysis', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(params)
        });

        const result = await response.json();

        console.log('Analysis response:', result);

        if (result.error) {
            console.error('Analysis error details:', {
                error: result.error,
                stdout: result.stdout,
                stderr: result.stderr,
                hint: result.hint
            });

            let errorMsg = result.error;
            if (result.stderr) {
                errorMsg += `\n\nScript error output:\n${result.stderr}`;
            }
            if (result.hint) {
                errorMsg += `\n\nHint: ${result.hint}`;
            }

            throw new Error(errorMsg);
        }

        // Success - reload cards
        statusMsg.textContent = 'Analysis complete! Reloading...';

        await loadAnalysisCards();

        // Close modal
        setTimeout(() => {
            document.getElementById('new-analysis-modal').style.display = 'none';
            form.style.display = 'block';
            statusDiv.style.display = 'none';
        }, 1000);

    } catch (error) {
        console.error('Analysis error:', error);

        let displayMsg = error.message;
        if (displayMsg.length > 200) {
            displayMsg = displayMsg.substring(0, 200) + '... (see console for full error)';
        }

        statusMsg.textContent = `Error: ${displayMsg}`;
        statusMsg.style.color = 'var(--red)';

        setTimeout(() => {
            form.style.display = 'block';
            statusDiv.style.display = 'none';
            statusMsg.style.color = 'var(--green)';
        }, 5000);
    }
}

// Show error message
function showError(message) {
    alert(message);
}
