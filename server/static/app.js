document.addEventListener('alpine:init', () => {
    Alpine.data('companyList', () => ({
        companies: [],
        loading: false,
        
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
        }
    }));
});
