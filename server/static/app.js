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
                company.research_task_id = data.task_id;
                company.research_status = data.status;
                
                // Start polling for updates
                this.pollResearchStatus(company);
            } catch (err) {
                console.error('Failed to research company:', err);
                this.researchingCompanies.delete(company.name);
            }
        },

        async pollResearchStatus(company) {
            while (this.researchingCompanies.has(company.name)) {
                try {
                    const response = await fetch(`/api/research/${company.research_task_id}`);
                    const task = await response.json();
                    
                    company.research_status = task.status;
                    
                    if (task.status === 'completed') {
                        // Update company with research results
                        if (task.result) {
                            Object.assign(company, task.result);
                        }
                        this.researchingCompanies.delete(company.name);
                        break;
                    } else if (task.status === 'failed') {
                        company.research_error = task.error;
                        this.researchingCompanies.delete(company.name);
                        break;
                    }
                    
                    // Wait before polling again
                    await new Promise(resolve => setTimeout(resolve, 1000));
                } catch (err) {
                    console.error('Failed to poll research status:', err);
                    this.researchingCompanies.delete(company.name);
                    break;
                }
            }
        },

        getResearchStatusText(company) {
            if (company.research_error) {
                return `Research failed: ${company.research_error}`;
            }
            switch (company.research_status) {
                case 'pending':
                    return 'Research pending...';
                case 'running':
                    return 'Researching...';
                case 'completed':
                    return 'Research complete';
                case 'failed':
                    return 'Research failed';
                default:
                    return '';
            }
        },

        getResearchStatusClass(company) {
            return {
                'status-pending': company.research_status === 'pending',
                'status-running': company.research_status === 'running',
                'status-completed': company.research_status === 'completed',
                'status-failed': company.research_status === 'failed' || company.research_error
            };
        },

        isResearching(company) {
            return this.researchingCompanies.has(company.name);
        }
    }));
});
