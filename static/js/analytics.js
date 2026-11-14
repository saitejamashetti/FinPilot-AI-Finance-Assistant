const trendCanvas = document.getElementById('trendChart');
if (trendCanvas) {
    const labels = JSON.parse(trendCanvas.dataset.labels || '[]');
    const values = JSON.parse(trendCanvas.dataset.values || '[]');

    new Chart(trendCanvas, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Expenses',
                data: values,
                borderColor: '#0f766e',
                fill: false,
                tension: 0.3,
            }],
        },
        options: {
            maintainAspectRatio: false,
            scales: { y: { beginAtZero: true } },
        },
    });
}
