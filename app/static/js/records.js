/**
 * File upload preview & dropzone interactions for MediVault
 */

document.addEventListener('DOMContentLoaded', () => {
    // Dropzone file selector feedback
    const dropzone = document.getElementById('upload-dropzone');
    const fileInput = document.getElementById('document_file');
    const fileDetailsBox = document.getElementById('file-details-preview');
    const fileNameSpan = document.getElementById('selected-file-name');
    const fileSizeSpan = document.getElementById('selected-file-size');

    if (dropzone && fileInput) {
        dropzone.addEventListener('click', () => {
            fileInput.click();
        });

        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });

        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });

        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                updateFilePreview(fileInput.files[0]);
            }
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                updateFilePreview(fileInput.files[0]);
            }
        });
    }

    function updateFilePreview(file) {
        if (!file || !fileDetailsBox) return;
        fileDetailsBox.classList.remove('d-none');
        if (fileNameSpan) fileNameSpan.textContent = file.name;
        if (fileSizeSpan) {
            const sizeInKb = (file.size / 1024).toFixed(1);
            const sizeText = file.size > 1024 * 1024 
                ? (file.size / (1024 * 1024)).toFixed(2) + ' MB' 
                : sizeInKb + ' KB';
            fileSizeSpan.textContent = sizeText;
        }
    }

    // Auto submit filter selects if present
    const categorySelect = document.getElementById('filter-category');
    const sortSelect = document.getElementById('filter-sort');
    const filterForm = document.getElementById('filter-records-form');

    if (filterForm) {
        if (categorySelect) {
            categorySelect.addEventListener('change', () => filterForm.submit());
        }
        if (sortSelect) {
            sortSelect.addEventListener('change', () => filterForm.submit());
        }
    }
});
