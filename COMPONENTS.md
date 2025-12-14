# Pool Cue UI Components Reference

Standard UI patterns used across all templates. Follow these for consistency.

## CSS Variables (Standard)

```css
:root {
    /* Backgrounds */
    --bg-primary: #111111;
    --bg-secondary: #1a1a1a;
    --bg-tertiary: #222222;
    
    /* Text */
    --text-primary: #f2f2f2;
    --text-secondary: #888888;
    --text-muted: #555555;
    
    /* Accents */
    --accent: #f5c518;        /* Pool Cue yellow */
    --accent-dim: rgba(245, 197, 24, 0.15);
    --success: #22c55e;       /* Green */
    --error: #ef4444;         /* Red */
    --blue: #3b82f6;
    
    /* Borders */
    --border: rgba(255,255,255,0.1);
    
    /* Rankings */
    --gold: #ffd700;
    --silver: #c0c0c0;
    --bronze: #cd7f32;
}
```

## Buttons

### Primary Action Button
```css
.btn-primary {
    padding: 14px 24px;
    background: linear-gradient(135deg, var(--accent), #e0b015);
    border: none;
    border-radius: 12px;
    color: #111;
    font-size: 1rem;
    font-weight: 700;
    cursor: pointer;
}
```

### Secondary Button
```css
.btn-secondary {
    padding: 12px 20px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--text-primary);
    font-weight: 600;
}
```

### Small Header Button
```css
.header-btn {
    padding: 10px 14px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-secondary);
    font-size: 0.8rem;
    font-weight: 500;
}
```

## Border Radius Standards

| Element | Radius |
|---------|--------|
| Primary buttons | 12px |
| Cards/containers | 12px |
| Secondary buttons | 8px |
| Input fields | 8px |
| Back buttons | 8px |
| Small elements | 6px |
| Avatars | 50% (circle) |

## Page Header

```css
.header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
}
```

## Back Button

```css
.back-btn {
    width: 36px;
    height: 36px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-primary);
    font-size: 1.2rem;
    display: flex;
    align-items: center;
    justify-content: center;
    text-decoration: none;
}
```

## Bottom Navigation (Player App)

```css
.bottom-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--bg-primary);
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: space-around;
    padding: 6px 0 22px;  /* 22px for iPhone safe area */
    z-index: 100;
}

.nav-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-decoration: none;
    color: var(--text-muted);
    font-size: 0.7rem;
    gap: 4px;
}

.nav-item.active {
    color: var(--accent);
}
```

## Cards

### Standard Card
```css
.card {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
}
```

### Stat Box
```css
.stat-box {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 10px;
    text-align: center;
}
```

## Form Inputs

```css
input, select, textarea {
    width: 100%;
    padding: 14px 16px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-primary);
    font-size: 1rem;
    font-family: inherit;
}

input:focus {
    outline: none;
    border-color: var(--accent);
}
```

## Toast Notifications

```javascript
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 100px;
        left: 50%;
        transform: translateX(-50%);
        padding: 12px 20px;
        background: ${type === 'success' ? 'var(--success)' : 'var(--accent)'};
        color: #111;
        border-radius: 8px;
        font-size: 0.85rem;
        font-weight: 600;
        z-index: 10000;
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}
```

## Status Badges

```css
.badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
}

.badge-success { background: rgba(34,197,94,0.15); color: #22c55e; }
.badge-warning { background: rgba(245,197,24,0.15); color: #f5c518; }
.badge-error { background: rgba(239,68,68,0.15); color: #ef4444; }
```

## Body Padding

Always include bottom padding for bottom nav:
```css
body {
    padding-bottom: 100px;  /* Space for bottom nav */
}
```

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-12 | Initial components reference created |
