document.addEventListener('alpine:init', () => {
    Alpine.data('companyList', () => ({
        companies: [],
        loading: false,
        editingCompany: null,
        editingReply: '',
        
        async init() {
            this.loading = true;
            try {
                const response = await fetch('/api/companies');
                this.companies = await response.json();
            } catch (err) {
                console.error('Failed to load companies:', err);
            } finally {
                this.loading = false;
            }
        },

        async generateReply(company) {
            try {
                const response = await fetch(`/api/${company.name}/generate_message`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ name: company.name }),
                });
                
                const data = await response.json();
                
                // Update the company's reply_message in the local state
                company.reply_message = data.message;
            } catch (err) {
                console.error('Failed to generate reply:', err);
            }
        },

        editReply(company) {
            this.editingCompany = company;
            this.editingReply = company.reply_message;
            document.getElementById('editModal').showModal();
        },

        cancelEdit() {
            this.editingCompany = null;
            this.editingReply = '';
            document.getElementById('editModal').close();
        },

        saveReply() {
            if (this.editingCompany) {
                this.editingCompany.reply_message = this.editingReply;
                this.cancelEdit();
            }
        }
    }));
});
