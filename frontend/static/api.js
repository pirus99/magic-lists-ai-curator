(function (window) {
    const api = {
        async get(path) {
            const resp = await fetch(path);
            if (!resp.ok) throw new Error(`API GET ${path} failed: ${resp.status}`);
            return resp.json();
        },
        async post(path, body) {
            const resp = await fetch(path, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (!resp.ok) throw new Error(`API POST ${path} failed: ${resp.status}`);
            return resp.json();
        }
    };

    window.App = window.App || {};
    window.App.api = api;
})(window);
