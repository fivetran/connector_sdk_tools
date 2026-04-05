/**
 * Shared validation utilities for project names across all components
 */

export interface Connector {
  name: string
  [key: string]: any
}

/**
 * Validates a project name according to the following rules:
 * - Required (cannot be empty)
 * - Max 255 characters
 * - No spaces
 * - No capital letters
 * - Cannot begin with a number
 * - Only lowercase letters, numbers, and underscores allowed
 * - Must be unique (not in existing connectors list)
 *
 * @param name - The project name to validate
 * @param existingConnectors - Array of existing connectors to check uniqueness
 * @returns Empty string if valid, error message if invalid
 */
export const validateProjectName = (name: string, existingConnectors: Connector[] = []): string => {
  if (!name.trim()) {
    return 'Project name is required'
  }

  if (name.trim().length > 255) {
    return 'Project name must be 255 characters or less'
  }

  // Check for spaces
  if (/\s/.test(name)) {
    return 'Project name cannot contain spaces'
  }

  // Check for capital letters
  if (/[A-Z]/.test(name)) {
    return 'Project name cannot contain capital letters'
  }

  // Check if starts with number
  if (/^[0-9]/.test(name.trim())) {
    return 'Project name cannot begin with a number'
  }

  // Check for valid characters (must start with letter or underscore, followed by letters, numbers, or underscores)
  if (!/^[a-z_][a-z0-9_]*$/.test(name.trim())) {
    return 'Project name can only contain lowercase letters, numbers, and underscores'
  }

  // Check if project already exists
  const existingConnector = existingConnectors.find(connector =>
    connector.name.toLowerCase() === name.trim().toLowerCase()
  )
  if (existingConnector) {
    return 'A project with this name already exists'
  }

  return ''
}
