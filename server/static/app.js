document.addEventListener('alpine:init', () => {
    Alpine.data('companyList', () => ({
        companies: [],
        loading: false,
        editingCompany: null,
        editingReply: '',
        researchingCompanies: new Set(),
        generatingMessages: new Set(),
        
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
                this.generatingMessages.add(company.name);
                const response = await fetch(`/api/${company.name}/reply_message`, {
                    method: 'POST',
                });
                
                const data = await response.json();
                company.message_task_id = data.task_id;
                company.message_status = data.status;
                
                // Start polling for updates
                this.pollMessageStatus(company);
            } catch (err) {
                console.error('Failed to generate reply:', err);
                this.generatingMessages.delete(company.name);
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
            return this.pollTaskStatus(company, 'research');
        },

        getResearchStatusText(company) {
            return this.getTaskStatusText(company, 'research');
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
        },

        async pollMessageStatus(company) {
            return this.pollTaskStatus(company, 'message');
        },

        getMessageStatusText(company) {
            return this.getTaskStatusText(company, 'message');
        },

        isGeneratingMessage(company) {
            return this.generatingMessages.has(company.name);
        },

        async pollTaskStatus(company, taskType) {
            const isMessage = taskType === 'message';
            const trackingSet = isMessage ? this.generatingMessages : this.researchingCompanies;
            const taskIdField = isMessage ? 'message_task_id' : 'research_task_id';
            const statusField = isMessage ? 'message_status' : 'research_status';
            const errorField = isMessage ? 'message_error' : 'research_error';

            while (trackingSet.has(company.name)) {
                try {
                    const response = await fetch(`/api/tasks/${company[taskIdField]}`);
                    const task = await response.json();
                    
                    company[statusField] = task.status;
                    
                    if (task.status === 'completed') {
                        if (isMessage && task.result?.message) {
                            company.reply_message = task.result.message;
                        } else if (!isMessage && task.result) {
                            Object.assign(company, task.result);
                        }
                        trackingSet.delete(company.name);
                        break;
                    } else if (task.status === 'failed') {
                        company[errorField] = task.error;
                        trackingSet.delete(company.name);
                        break;
                    }
                    
                    await new Promise(resolve => setTimeout(resolve, 1000));
                } catch (err) {
                    console.error(`Failed to poll ${taskType} status:`, err);
                    trackingSet.delete(company.name);
                    break;
                }
            }
        },

        getTaskStatusText(company, taskType) {
            const isMessage = taskType === 'message';
            const status = isMessage ? company.message_status : company.research_status;
            const error = isMessage ? company.message_error : company.research_error;
            const action = isMessage ? 'Generation' : 'Research';

            if (error) {
                return `${action} failed: ${error}`;
            }
            switch (status) {
                case 'pending':
                    return isMessage ? 'Generating message...' : 'Research pending...';
                case 'running':
                    return isMessage ? 'Generating...' : 'Researching...';
                case 'completed':
                    return isMessage ? 'Message generated' : 'Research complete';
                case 'failed':
                    return `${action} failed`;
                default:
                    return '';
            }
        }
    }));
});
