const categoryCanvas = document.getElementById('categoryChart');
if (categoryCanvas) {
    const categoryData = JSON.parse(categoryCanvas.dataset.categories || '[]');
    const palette = ['#0f766e', '#34d399', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#f97316', '#64748b'];

    new Chart(categoryCanvas, {
        type: 'doughnut',
        data: {
            labels: categoryData.map((item) => item.label),
            datasets: [{
                data: categoryData.map((item) => item.value),
                backgroundColor: palette.slice(0, categoryData.length),
                borderWidth: 0,
            }],
        },
        options: {
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
        },
    });
}
