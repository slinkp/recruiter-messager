document.addEventListener('alpine:init', () => {
    Alpine.data('companyList', () => ({
        companies: [],
        loading: false,
        editingCompany: null,
        editingReply: '',
        researchingCompanies: new Set(),
        
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
                const response = await fetch(`/api/${company.name}/reply_message`, {
                    method: 'POST',
                });
                
                const data = await response.json();
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

        async saveReply() {
            if (this.editingCompany) {
                try {
                    const response = await fetch(`/api/${this.editingCompany.name}/reply_message`, {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ message: this.editingReply }),
                    });
                    
                    const data = await response.json();
                    if (response.ok) {
                        this.editingCompany.reply_message = data.message;
                        this.cancelEdit();
                    } else {
                        console.error('Failed to save reply:', data.error);
                    }
                } catch (err) {
                    console.error('Failed to save reply:', err);
                }
            }
        },

        async research(company) {
            try {
                this.researchingCompanies.add(company.name);
                const response = await fetch(`/api/${company.name}/research`, {
                    method: 'POST',
                });
                
                const data = await response.json();
                Object.assign(company, data);
            } catch (err) {
                console.error('Failed to research company:', err);
            } finally {
                this.researchingCompanies.delete(company.name);
            }
        },

        isResearching(company) {
            return this.researchingCompanies.has(company.name);
        }
    }));
});
