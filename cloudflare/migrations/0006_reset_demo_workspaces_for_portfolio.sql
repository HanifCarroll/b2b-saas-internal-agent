-- Demo workspaces are disposable. Recreate them with the persistent request portfolio.
DELETE FROM workspaces WHERE identity_mode = 'demo';
