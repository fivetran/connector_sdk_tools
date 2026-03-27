import { useState, useEffect, useRef, type ReactElement } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Editor from '@monaco-editor/react'
import DatabaseViewer from './DatabaseViewer'
import { validateProjectName } from './utils/validation'

// API Base URL configuration
// When running locally: use direct backend connection
// When running via nginx: use /api prefix (nginx proxies to backend)
const host = window.location.hostname
const port = '8001'

const API_BASE = (host === 'localhost' || host === '127.0.0.1')
  ? `http://localhost:${port}`
  : `/api`

// Google Client ID is fetched from the backend at runtime (see LoginPage)

// App name and version - change these to update everywhere
const APP_NAME = 'AI Connector Builder'
const APP_VERSION = '0.3.2.2'

// Authenticated fetch wrapper that handles session expiration globally
const authenticatedFetch = async (url: string, options: RequestInit = {}) => {
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
  })

  if (response.status === 401) {
    localStorage.removeItem('username')
    window.location.href = '/'
    throw new Error('Session expired - redirecting to login')
  }

  return response
}

// Tooltip component
const Tooltip = ({ children, text }: { children: React.ReactNode, text: string }) => {
  const [isVisible, setIsVisible] = useState(false)

  return (
    <div 
      style={{ position: 'relative', display: 'inline-block' }}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children}
      {isVisible && (
        <div style={{
          position: 'absolute',
          bottom: '100%',
          left: '50%',
          transform: 'translateX(-50%)',
          backgroundColor: '#1a1a1a',
          color: '#FDFCFB',
          padding: '8px 12px',
          borderRadius: '6px',
          fontSize: '12px',
          whiteSpace: 'nowrap',
          zIndex: 1000,
          border: '1px solid #333',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
          marginBottom: '8px'
        }}>
          {text}
          <div style={{
            position: 'absolute',
            top: '100%',
            left: '50%',
            transform: 'translateX(-50%)',
            border: '4px solid transparent',
            borderTopColor: '#1a1a1a'
          }}></div>
      </div>
      )}
    </div>
  )
}

function useAuth() {
  const loggedIn = typeof window !== 'undefined' && !!localStorage.getItem('username')
  return { loggedIn }
}

function ProtectedRoute({ children }: { children: ReactElement }) {
  const { loggedIn } = useAuth()
  if (!loggedIn) {
    return <Navigate to="/" replace />
  }
  return children
}

function RootRedirect() {
  const { loggedIn } = useAuth()
  if (loggedIn) {
    return <Navigate to="/home" replace />
  }
  return <LoginPage />
}

function LoginPage() {
  const [error, setError] = useState('')
  const [googleClientId, setGoogleClientId] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    fetch(`${API_BASE}/auth/config`)
      .then(res => res.json())
      .then(data => setGoogleClientId(data.google_client_id || ''))
      .catch(() => setError('Failed to load login configuration'))
  }, [])

  const handleGoogleLogin = async (credentialResponse: any) => {
    setError('')

    if (!credentialResponse?.credential) {
      setError('Google login failed')
      return
    }

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: credentialResponse.credential }),
        credentials: 'include',
      })

      const data = await res.json()

      if (data.success) {
        localStorage.setItem('username', data.username)
        navigate('/home', { replace: true })
      } else {
        setError(data.detail || data.message || 'Login failed')
      }
    } catch (err) {
      console.error(err)
      setError('Login failed: Server error')
    }
  }

  if (!googleClientId) {
    return (
      <div style={{ width: '100vw', height: '100vh', background: '#1B1818', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff' }}>
        {error || 'Loading...'}
      </div>
    )
  }

  return (
    <GoogleOAuthProvider clientId={googleClientId}>
      <div
        className="login-page page-fade-in"
        style={{
          width: '100vw',
          height: '100vh',
          position: 'fixed',
          top: 0,
          left: 0,
          background: '#1B1818',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {/* Background gradient */}
        <div style={{
          position: 'absolute',
          width: '100%',
          height: '100%',
          background:
            'radial-gradient(ellipse 77% 51% at 50% 130%, rgba(48,107,234,0.5) 0%, rgba(48,107,234,0) 80%), ' +
            'radial-gradient(ellipse 103% 70% at 50% 130%, rgba(48,107,234,0.3) 0%, rgba(48,107,234,0) 100%)',
          zIndex: 0,
        }} />

        {/* Content */}
        <div style={{
          position: 'relative',
          zIndex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '30px',
          color: '#FDFCFB',
        }}>
          {/* Header */}
          <div style={{ textAlign: 'center' }}>
            <img
              src="/fivetran-mark-white-rgb.png"
              alt="Fivetran"
              style={{ height: '60px', marginBottom: '15px' }}
            />
            <h1 style={{ fontSize: '36px', margin: 0 }}>{APP_NAME} <span style={{ fontSize: '14px', color: '#9b948f', fontWeight: 'normal' }}>(v{APP_VERSION})</span></h1>
          </div>

          {/* Description */}
          <p style={{ fontSize: '14px', lineHeight: '20px', maxWidth: '700px', textAlign: 'center', margin: 0 }}>
            Welcome to Fivetran's {APP_NAME}, your AI Agent for building custom connectors. It will help you create or upload a connector, define the data to pull from your source, test and edit, save progress, optimize and deploy your connector.
          </p>

          {/* Google Login */}
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '20px',
          }}>
            <div style={{ colorScheme: 'light' }}>
              <GoogleLogin
                onSuccess={handleGoogleLogin}
                onError={() => setError('Google login failed')}
                theme="filled_black"
                size="large"
                text="signin_with"
                width="400"
              />
            </div>
          </div>

          {/* Warning Banner */}
          <br />
          <div style={{
            background: 'linear-gradient(135deg, #ff6b35 0%, #f7931e 100%)',
            border: '1px solid #ff6b35',
            borderRadius: '8px',
            padding: '8px 16px',
            boxShadow: '0 4px 12px rgba(255, 107, 53, 0.3)',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '10px'
          }}>
            <div style={{ fontSize: '18px', color: '#fff' }}>⚠️</div>
            <div style={{
              color: '#fff',
              fontSize: '14px',
              fontWeight: '600',
              whiteSpace: 'nowrap'
            }}>
              Warning: This tool is in Early Access. Use at your own risk.
            </div>
          </div>

          {/* Error */}
          {error && (
            <div style={{ color: '#FF6B6B', fontSize: '14px' }}>
              {error}
            </div>
          )}
        </div>
      </div>
    </GoogleOAuthProvider>
  )
}

function HomePage() {
  const username = localStorage.getItem('username') || 'User'
  const navigate = useNavigate()
  const [connectors, setConnectors] = useState<Array<{name: string, display_name: string, description: string, version: string}>>([])
  const [selectedConnector, setSelectedConnector] = useState('')
  const [loadingConnectors, setLoadingConnectors] = useState(false)
  const [showUploadWizard, setShowUploadWizard] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null)
  const [selectedFileObjects, setSelectedFileObjects] = useState<File[]>([])
  const [excludedFiles, setExcludedFiles] = useState<Set<string>>(new Set())
  const [uploadProgress, setUploadProgress] = useState(0)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProjectName, setUploadProjectName] = useState('')
  const [projectNameError, setProjectNameError] = useState('')

  const handleLogout = async () => {
    try {
      await authenticatedFetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
      })
    } catch (error) {
      console.error('Error during logout:', error)
    } finally {
      localStorage.removeItem('username')
      navigate('/', { replace: true })
    }
  }

  // Load user's connectors on component mount
  useEffect(() => {
    const loadConnectors = async () => {
      setLoadingConnectors(true)
      try {
        const response = await authenticatedFetch(`${API_BASE}/user-connectors/${username}`)
        const data = await response.json()
        if (data.success) {
          setConnectors(data.connectors)
        }
      } catch (error) {
        console.error('Error loading connectors:', error)
      } finally {
        setLoadingConnectors(false)
      }
    }
    
    loadConnectors()
  }, [username])

  const handleConnectorSelect = (connectorName: string) => {
    if (connectorName) {
      // Store the selected connector and navigate to AI Builder
      // AIBuilderPage will check if connector.py exists and generate if needed
      localStorage.setItem('current_project_name', connectorName)
      navigate('/ai-builder')
    }
  }

  // Files and folders to exclude from upload (common unwanted files)
  const UPLOAD_EXCLUDE_PATTERNS = [
    '.DS_Store',
    '__pycache__',
    '.pyc',
    '.pyo',
    '.git',
    '.gitignore',
    '.venv',
    'venv',
    '.env',
    'node_modules',
    '.idea',
    '.vscode',
    'warehouse.db',
    'files/',
  ]

  const shouldExcludeFile = (file: File): boolean => {
    const relativePath = (file as any).webkitRelativePath || file.name
    const fileName = relativePath.split('/').pop() || ''
    const pathParts = relativePath.split('/')

    // Check if any part of the path matches exclude patterns
    for (const pattern of UPLOAD_EXCLUDE_PATTERNS) {
      if (fileName === pattern) return true
      if (fileName.endsWith(pattern)) return true
      if (pathParts.some(part => part === pattern)) return true
    }
    return false
  }

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files
    if (files && files.length > 0) {
      const fileArray = convertFileListToArray(files)

      // Filter out excluded files
      const filteredArray = fileArray.filter(file => !shouldExcludeFile(file))

      // Check if connector.py exists in the selected folder
      const hasConnectorPy = filteredArray.some(file => {
        const fileName = ((file as any).webkitRelativePath || file.name).split('/').pop()
        return fileName === 'connector.py'
      })

      if (!hasConnectorPy) {
        alert('Missing connector.py - a connector.py file is required to upload a project. Please select a different folder.')
        // Reset the file input
        event.target.value = ''
        return
      }

      // Auto-fill project name from folder name if the input is empty
      if (!uploadProjectName.trim()) {
        const firstPath = (filteredArray[0] as any).webkitRelativePath || ''
        const folderName = firstPath.split('/')[0]
        if (folderName) {
          setUploadProjectName(folderName)
        }
      }

      setSelectedFiles(files)
      setSelectedFileObjects(filteredArray)
      setExcludedFiles(new Set()) // Reset exclusions when new files selected
    }
  }

  const handleUpload = async () => {
    const filteredFiles = getFilteredFiles()
    if (filteredFiles.length === 0) return

    // Check if connector.py is included in the upload
    const hasConnectorPy = filteredFiles.some(file => {
      const fileName = ((file as any).webkitRelativePath || file.name).split('/').pop()
      return fileName === 'connector.py'
    })
    if (!hasConnectorPy) {
      alert('Upload requires a connector.py file. Please include connector.py in your project.')
      return
    }

    // Validate project name before proceeding
    const nameError = validateProjectName(uploadProjectName, connectors)
    if (nameError) {
      setProjectNameError(nameError)
      return
    }

    setIsUploading(true)
    setUploadProgress(0)

    try {
      const formData = new FormData()
      
      // Add only the filtered (non-excluded) files to FormData
      filteredFiles.forEach(file => {
        formData.append('files', file)
      })
      formData.append('username', username)
      formData.append('project_name', uploadProjectName.trim())

      const response = await authenticatedFetch(`${API_BASE}/upload-connector`, {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()

      // Handle HTTP error responses
      if (!response.ok) {
        const errorMessage = data.detail || data.message || 'Upload failed'
        alert(`Upload failed: ${errorMessage}`)
        return
      }

      if (data.success) {
        // Upload successful, close wizard and navigate to AI Builder
        setShowUploadWizard(false)
        setSelectedFiles(null)
        setUploadProgress(0)

        // Set the uploaded connector as current project
        localStorage.setItem('current_project_name', data.connector_name)

        // Reload connectors list
        const connectorsResponse = await fetch(`${API_BASE}/user-connectors/${username}`, {
          credentials: 'include',
        })
        const connectorsData = await connectorsResponse.json()
        if (connectorsData.success) {
          setConnectors(connectorsData.connectors)
        }

        // Navigate to AI Builder - it will check for connector.py and load/generate accordingly
        navigate('/ai-builder')
      } else {
        alert(`Upload failed: ${data.message}`)
      }
    } catch (error) {
      console.error('Upload error:', error)
      alert('Upload failed: Server error')
    } finally {
      setIsUploading(false)
    }
  }

  const handleProjectNameChange = (value: string) => {
    setUploadProjectName(value)
    const error = validateProjectName(value, connectors)
    setProjectNameError(error)
  }

  // File utility functions
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const getFileIcon = (filename: string): string => {
    const ext = filename.split('.').pop()?.toLowerCase()
    switch (ext) {
      case 'py': return '🐍'
      case 'json': return '📋'
      case 'md': return '📝'
      case 'txt': return '📄'
      case 'yaml':
      case 'yml': return '⚙️'
      default: return '📄'
    }
  }

  const getUniqueFileKey = (file: File): string => {
    // Use webkitRelativePath if available, otherwise filename + size + lastModified
    const relativePath = (file as any).webkitRelativePath || file.name
    return `${relativePath}-${file.size}-${file.lastModified}`
  }

  const convertFileListToArray = (fileList: FileList): File[] => {
    return Array.from(fileList)
  }

  const getFilteredFiles = (): File[] => {
    return selectedFileObjects.filter(file => !excludedFiles.has(getUniqueFileKey(file)))
  }

  const hasConnectorPyInSelection = (): boolean => {
    return getFilteredFiles().some(file => {
      const fileName = ((file as any).webkitRelativePath || file.name).split('/').pop()
      return fileName === 'connector.py'
    })
  }

  const groupFilesByDirectory = (files: File[]): { [dir: string]: File[] } => {
    const groups: { [dir: string]: File[] } = {}
    
    files.forEach(file => {
      const relativePath = (file as any).webkitRelativePath || file.name
      const pathParts = relativePath.split('/')
      const directory = pathParts.length > 1 ? pathParts.slice(0, -1).join('/') : 'Root'
      
      if (!groups[directory]) {
        groups[directory] = []
      }
      groups[directory].push(file)
    })
    
    return groups
  }

  // File selection/deselection functions
  const toggleFileSelection = (file: File) => {
    const fileKey = getUniqueFileKey(file)
    const newExcludedFiles = new Set(excludedFiles)
    
    if (excludedFiles.has(fileKey)) {
      newExcludedFiles.delete(fileKey)
    } else {
      newExcludedFiles.add(fileKey)
    }
    
    setExcludedFiles(newExcludedFiles)
  }

  const toggleDirectorySelection = (directory: string, files: File[]) => {
    const newExcludedFiles = new Set(excludedFiles)
    const directoryFiles = files.map(file => getUniqueFileKey(file))
    
    // Check if all files in directory are currently selected (not excluded)
    const allSelected = directoryFiles.every(fileKey => !excludedFiles.has(fileKey))
    
    if (allSelected) {
      // Exclude all files in directory
      directoryFiles.forEach(fileKey => newExcludedFiles.add(fileKey))
    } else {
      // Include all files in directory
      directoryFiles.forEach(fileKey => newExcludedFiles.delete(fileKey))
    }
    
    setExcludedFiles(newExcludedFiles)
  }

  const selectAllFiles = () => {
    setExcludedFiles(new Set())
  }

  const deselectAllFiles = () => {
    const allFileKeys = selectedFileObjects.map(file => getUniqueFileKey(file))
    setExcludedFiles(new Set(allFileKeys))
  }

  const closeUploadWizard = () => {
    setShowUploadWizard(false)
    setSelectedFiles(null)
    setSelectedFileObjects([])
    setExcludedFiles(new Set())
    setUploadProgress(0)
    setIsUploading(false)
    setUploadProjectName('')
    setProjectNameError('')
  }

  return (
    <div className="page-fade-in" style={{ position: 'relative', height: '100vh', background: '#1B1818', color: '#FDFCFB', overflow: 'hidden' }}>
      <div
        style={{
          position: 'absolute',
          width: '100%',
          height: '100%',
          top: 0,
          left: 0,
          background:
            'radial-gradient(ellipse 77% 51% at 50% 130%, rgba(48,107,234,0.5) 0%, rgba(48,107,234,0) 80%), ' +
            'radial-gradient(ellipse 103% 70% at 50% 130%, rgba(48,107,234,0.3) 0%, rgba(48,107,234,0) 100%), ' +
            'radial-gradient(ellipse 112% 73% at 50% 130%, rgba(48,107,234,0.25) 0%, rgba(48,107,234,0) 100%)',
          zIndex: 0,
        }}
      />
      <div style={{ position: 'relative', zIndex: 1, width: '100%', maxWidth: 1200, margin: '0 auto', textAlign: 'center', padding: '20px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', gap: 20, boxSizing: 'border-box' }}>
        {/* Username + Logout Button */}
        <div style={{ position: 'fixed', top: '20px', right: '20px', zIndex: 10, display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ color: '#9b948f', fontSize: '14px' }}>{username}</span>
          <button
            onClick={handleLogout}
            style={{
              padding: '8px 16px',
              background: 'rgba(255, 255, 255, 0.1)',
              color: '#FDFCFB',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '14px',
              transition: 'all 0.2s ease'
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.2)'
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'
            }}
          >
            Logout
          </button>
        </div>
        
        <img 
          src="/fivetran-mark-white-rgb.png" 
          alt="Fivetran" 
          style={{ 
            height: '70px', 
            marginBottom: '10px',
            filter: 'brightness(0.9)'
          }} 
        />
        <h1 style={{ fontSize: 40, margin: 0 }}>{APP_NAME} <span style={{ fontSize: '14px', color: '#9b948f', fontWeight: 'normal' }}>(v{APP_VERSION})</span></h1>
        <p style={{ color: '#9b948f', margin: 0 }}>Your AI Agent for Connectors</p>
        <p style={{ color: '#bdb7b2', lineHeight: '24px', maxWidth: 900, margin: '8px auto 0' }}>
          Welcome {username}! Create or upload a connector, define a source, edit your code,
          automatically save progress, deploy, and optimize your connection.
        </p>
        <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap', marginTop: 16 }}>
          <Tooltip text="Create a new connector from scratch using our AI-powered builder">
            <button
              onClick={() => navigate('/create-connector')}
              style={{ padding: '12px 18px', background: '#306BEA', color: '#FDFCFB', border: 'none', borderRadius: 6, cursor: 'pointer', minWidth: 220 }}
            >
              Create connector
            </button>
          </Tooltip>
          <Tooltip text="Select a connector to load">
            <div style={{ position: 'relative', display: 'inline-block' }}>
              <button
                style={{
                  padding: '12px 18px',
                  background: '#263043',
                  color: '#FDFCFB',
                  border: 'none',
                  borderRadius: 6,
                  cursor: connectors.length === 0 ? 'not-allowed' : 'pointer',
                  minWidth: 220,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  opacity: connectors.length === 0 ? 0.6 : 1
                }}
                onClick={() => {
                  if (connectors.length > 0) {
                    const select = document.getElementById('connector-select') as HTMLSelectElement
                    select?.click()
                  }
                }}
              >
                <span>
                  {loadingConnectors ? 'Loading...' : 'Load connector'}
                </span>
                <span style={{ fontSize: '12px', marginLeft: '8px' }}>▼</span>
              </button>
              <select
                id="connector-select"
                value={selectedConnector}
                onChange={(e) => {
                  setSelectedConnector(e.target.value)
                  handleConnectorSelect(e.target.value)
                }}
                disabled={loadingConnectors || connectors.length === 0}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: '100%',
                  opacity: 0,
                  cursor: 'pointer',
                  appearance: 'none',
                  border: 'none',
                  background: 'transparent'
                }}
              >
                <option value="">
                  {loadingConnectors ? 'Loading...' : 'Load connector'}
                </option>
                {connectors.map((connector) => (
                  <option key={connector.name} value={connector.name}>
                    {connector.display_name}
                  </option>
                ))}
              </select>
            </div>
          </Tooltip>
          <Tooltip text="Upload an existing connector to get started">
            <button
              onClick={() => setShowUploadWizard(true)}
              style={{ padding: '12px 18px', background: '#263043', color: '#FDFCFB', border: 'none', borderRadius: 6, cursor: 'pointer', minWidth: 220 }}
            >
              Upload connector
            </button>
          </Tooltip>
        </div>
      </div>

      {/* Upload Wizard Modal */}
      {showUploadWizard && (
        <div className="modal-backdrop" style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div className="modal-content" style={{
            background: '#1B1818',
            borderRadius: '12px',
            padding: '32px',
            maxWidth: '600px',
            width: '90%',
            maxHeight: '80vh',
            overflow: 'auto',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            boxShadow: '0 20px 40px rgba(0, 0, 0, 0.5)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h2 style={{ margin: 0, fontSize: '24px', color: '#FDFCFB' }}>Upload Connector</h2>
              <button
                onClick={closeUploadWizard}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#9b948f',
                  fontSize: '24px',
                  cursor: 'pointer',
                  padding: '4px'
                }}
              >
                ×
              </button>
            </div>

            <div style={{ marginBottom: '24px' }}>
              <p style={{ color: '#bdb7b2', marginBottom: '16px', lineHeight: '1.5' }}>
                Select a directory containing your connector files. The wizard will upload all files in the selected directory.
              </p>
              
              {/* Project Name Input */}
              <div style={{ marginBottom: '20px' }}>
                <label style={{ 
                  display: 'block', 
                  color: '#FDFCFB', 
                  marginBottom: '8px', 
                  fontSize: '14px',
                  fontWeight: '500'
                }}>
                  Project Name <span style={{ color: '#ff6b35' }}>*</span>
                </label>
                <input
                  type="text"
                  value={uploadProjectName}
                  onChange={(e) => handleProjectNameChange(e.target.value)}
                  placeholder="Enter a unique project name"
                  style={{
                    width: '100%',
                    padding: '12px',
                    borderRadius: '6px',
                    border: projectNameError ? '1px solid #ff6b35' : '1px solid rgba(93,85,85,0.6)',
                    background: 'rgba(26,24,24,0.7)',
                    color: '#FDFCFB',
                    fontSize: '14px',
                    boxSizing: 'border-box'
                  }}
                />
                {projectNameError && (
                  <div style={{ 
                    color: '#ff6b35', 
                    fontSize: '12px', 
                    marginTop: '4px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}>
                    ⚠️ {projectNameError}
                  </div>
                )}
              </div>

              <div style={{
                border: '2px dashed #306BEA',
                borderRadius: '8px',
                padding: '32px',
                textAlign: 'center',
                background: 'rgba(48, 107, 234, 0.05)',
                cursor: 'pointer',
                transition: 'all 0.2s ease'
              }}>
                <input
                  type="file"
                  id="file-upload"
                  multiple
                  {...({ webkitdirectory: "" } as any)}
                  onChange={handleFileSelect}
                  style={{ display: 'none' }}
                />
                <label
                  htmlFor="file-upload"
                  style={{
                    cursor: 'pointer',
                    display: 'block',
                    color: '#306BEA',
                    fontSize: '16px',
                    fontWeight: '500'
                  }}
                >
                  📁 Click to select directory
                </label>
                <p style={{ color: '#9b948f', fontSize: '14px', marginTop: '8px' }}>
                  Select a folder containing your connector files
                </p>
              </div>

              {selectedFileObjects.length > 0 && (
                <div style={{ marginTop: '20px' }}>
                  {/* File Selection Header */}
                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between', 
                    alignItems: 'center', 
                    marginBottom: '12px' 
                  }}>
                    <h3 style={{ color: '#FDFCFB', fontSize: '16px', margin: 0 }}>
                      Files ({getFilteredFiles().length} of {selectedFileObjects.length} selected)
                    </h3>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        onClick={selectAllFiles}
                        style={{
                          padding: '4px 8px',
                          background: '#306BEA',
                          color: '#FDFCFB',
                          border: 'none',
                          borderRadius: '4px',
                          fontSize: '12px',
                          cursor: 'pointer'
                        }}
                      >
                        Select All
                      </button>
                      <button
                        onClick={deselectAllFiles}
                        style={{
                          padding: '4px 8px',
                          background: '#666',
                          color: '#FDFCFB',
                          border: 'none',
                          borderRadius: '4px',
                          fontSize: '12px',
                          cursor: 'pointer'
                        }}
                      >
                        Deselect All
                      </button>
                    </div>
                  </div>

                  {/* File List with Directory Grouping */}
                  <div style={{
                    background: '#2a2a2a',
                    borderRadius: '6px',
                    padding: '16px',
                    maxHeight: '300px',
                    overflow: 'auto'
                  }}>
                    {Object.entries(groupFilesByDirectory(selectedFileObjects)).map(([directory, files]) => (
                      <div key={directory} style={{ marginBottom: '16px' }}>
                        {/* Directory Header */}
                        <div 
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            marginBottom: '8px',
                            cursor: 'pointer',
                            padding: '4px',
                            borderRadius: '4px',
                            background: '#1a1a1a'
                          }}
                          onClick={() => toggleDirectorySelection(directory, files)}
                        >
                          <input
                            type="checkbox"
                            checked={files.every(file => !excludedFiles.has(getUniqueFileKey(file)))}
                            onChange={() => toggleDirectorySelection(directory, files)}
                            style={{
                              width: '16px',
                              height: '16px',
                              accentColor: '#306BEA'
                            }}
                          />
                          <span style={{ color: '#FDFCFB', fontSize: '14px', fontWeight: '500' }}>
                            📁 {directory === 'Root' ? 'Root Directory' : directory}
                          </span>
                          <span style={{ color: '#9b948f', fontSize: '12px' }}>
                            ({files.filter(file => !excludedFiles.has(getUniqueFileKey(file))).length}/{files.length})
                          </span>
                        </div>

                        {/* Files in Directory */}
                        <div style={{ paddingLeft: '24px' }}>
                          {files.map((file, index) => {
                            const fileKey = getUniqueFileKey(file)
                            const isSelected = !excludedFiles.has(fileKey)
                            const relativePath = (file as any).webkitRelativePath || file.name
                            const fileName = relativePath.split('/').pop() || file.name
                            
                            return (
                              <div 
                                key={fileKey}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '8px',
                                  padding: '4px',
                                  borderRadius: '4px',
                                  cursor: 'pointer',
                                  background: isSelected ? 'transparent' : 'rgba(153, 0, 0, 0.1)',
                                  borderBottom: index < files.length - 1 ? '1px solid #333' : 'none'
                                }}
                                onClick={() => toggleFileSelection(file)}
                              >
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={() => toggleFileSelection(file)}
                                  style={{
                                    width: '14px',
                                    height: '14px',
                                    accentColor: '#306BEA'
                                  }}
                                />
                                <span style={{ fontSize: '16px' }}>
                                  {getFileIcon(fileName)}
                                </span>
                                <span style={{ 
                                  color: isSelected ? '#bdb7b2' : '#666', 
                                  fontSize: '14px',
                                  flex: 1
                                }}>
                                  {fileName}
                                </span>
                                <span style={{ 
                                  color: '#9b948f', 
                                  fontSize: '12px',
                                  minWidth: '60px',
                                  textAlign: 'right'
                                }}>
                                  {formatFileSize(file.size)}
                                </span>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Warning when no files selected for upload */}
              {selectedFileObjects.length > 0 && getFilteredFiles().length === 0 && (
                <div style={{
                  marginTop: '20px',
                  padding: '12px',
                  background: 'rgba(255, 193, 7, 0.1)',
                  border: '1px solid rgba(255, 193, 7, 0.3)',
                  borderRadius: '6px',
                  color: '#ffc107',
                  fontSize: '14px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}>
                  ⚠️ No files selected for upload. Please select at least one file to proceed.
                </div>
              )}

              {isUploading && (
                <div style={{ marginTop: '20px' }}>
                  <div style={{
                    background: '#2a2a2a',
                    borderRadius: '6px',
                    padding: '16px',
                    textAlign: 'center'
                  }}>
                    <div style={{ color: '#FDFCFB', marginBottom: '8px' }}>Uploading...</div>
                    <div style={{
                      background: '#333',
                      borderRadius: '4px',
                      height: '8px',
                      overflow: 'hidden'
                    }}>
                      <div style={{
                        background: '#306BEA',
                        height: '100%',
                        width: `${uploadProgress}%`,
                        transition: 'width 0.3s ease'
                      }}></div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button
                onClick={closeUploadWizard}
                disabled={isUploading}
                style={{
                  padding: '12px 24px',
                  background: 'transparent',
                  color: '#9b948f',
                  border: '1px solid #333',
                  borderRadius: '6px',
                  cursor: isUploading ? 'not-allowed' : 'pointer',
                  opacity: isUploading ? 0.5 : 1
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleUpload}
                disabled={getFilteredFiles().length === 0 || !hasConnectorPyInSelection() || isUploading || !!projectNameError || !uploadProjectName.trim()}
                style={{
                  padding: '12px 24px',
                  background: getFilteredFiles().length > 0 && hasConnectorPyInSelection() && !isUploading && !projectNameError && uploadProjectName.trim() ? '#306BEA' : '#333',
                  color: '#FDFCFB',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: getFilteredFiles().length > 0 && hasConnectorPyInSelection() && !isUploading && !projectNameError && uploadProjectName.trim() ? 'pointer' : 'not-allowed',
                  opacity: getFilteredFiles().length > 0 && hasConnectorPyInSelection() && !isUploading && !projectNameError && uploadProjectName.trim() ? 1 : 0.5
                }}
              >
                {isUploading ? 'Uploading...' : 'Upload'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}



// Utility function to fix missing indentation in nested markdown lists
function fixNestedListIndentation(text: string): string {
  if (!text) return text

  const lines = text.split('\n')
  const fixedLines: string[] = []
  let insideNestedList = false
  let insideNumberedList = false

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmedLine = line.trim()

    // Check if this is a numbered list item (e.g., "1. ", "2. ")
    const isNumberedItem = /^\d+\.\s/.test(trimmedLine)

    if (isNumberedItem) {
      insideNumberedList = true
      insideNestedList = false
      fixedLines.push(line)
      continue
    }

    // Check if this line ends with colon (indicates nested items follow)
    if (trimmedLine.endsWith(':') && !insideNumberedList) {
      insideNestedList = true
      fixedLines.push(line)
      continue
    }

    // Check if we've hit a new field marker (exit nested list mode)
    if (trimmedLine.startsWith('**') || trimmedLine.startsWith('- **')) {
      insideNestedList = false
      insideNumberedList = false
      fixedLines.push(line)
      continue
    }

    // Handle nested items under numbered lists
    if (insideNumberedList && trimmedLine.length > 0) {
      // Check if it's the next numbered item
      if (/^\d+\.\s/.test(trimmedLine)) {
        fixedLines.push(line)
        continue
      }

      // Check if already indented with bullet
      if (trimmedLine.startsWith('- ')) {
        // Make sure it has proper indentation (3 spaces for numbered list sub-items)
        if (!line.startsWith('   ')) {
          fixedLines.push('   ' + trimmedLine)
        } else {
          fixedLines.push(line)
        }
      }
      // Plain text that should become a sub-bullet
      else if (!trimmedLine.startsWith('**')) {
        fixedLines.push('   - ' + trimmedLine)
      }
      else {
        fixedLines.push(line)
      }
      continue
    }

    // Handle nested items under items ending with colon (assumptions section)
    if (insideNestedList && trimmedLine.length > 0) {
      // Check if line already starts with proper markdown list format
      if (trimmedLine.startsWith('- ')) {
        // Already has bullet, just needs indentation (2 spaces)
        if (!line.startsWith('  ')) {
          fixedLines.push('  ' + trimmedLine)
        } else {
          fixedLines.push(line)
        }
      }
      // Check if this is a plain text item
      else if (!trimmedLine.startsWith('**')) {
        // Convert plain text to markdown list item with indentation
        fixedLines.push('  - ' + trimmedLine)
      }
      else {
        fixedLines.push(line)
      }
      continue
    }

    // Default: just push the line as-is
    fixedLines.push(line)
  }

  return fixedLines.join('\n')
}

function CreateConnectorPage() {
  const [projectName, setProjectName] = useState('')
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)
  const [generationStatus, setGenerationStatus] = useState('')
  const [errors, setErrors] = useState<string[]>([])
  
  // Simplified validation states
  const [validationLoading, setValidationLoading] = useState(false)
  const [validationProgressMessage, setValidationProgressMessage] = useState('')
  const [validationSuggestions, setValidationSuggestions] = useState<string[]>([])
  const [validationPassed, setValidationPassed] = useState(false)
  const [validationAttempted, setValidationAttempted] = useState(false)
  const [validationSuccessMessage, setValidationSuccessMessage] = useState('')
  const [validationAssumptions, setValidationAssumptions] = useState('')
  const [validationSessionActive, setValidationSessionActive] = useState(false)
  const [showPromptViewer, setShowPromptViewer] = useState(false)
  const [enhancedDescription, setEnhancedDescription] = useState('')

  // Chat-based validation conversation history
  type ValidationMessage = {
    role: 'user' | 'assistant'
    content: string
    timestamp: number
  }
  const [validationConversation, setValidationConversation] = useState<ValidationMessage[]>([])
  const [currentInput, setCurrentInput] = useState('')
  const [inputModifiedSinceValidation, setInputModifiedSinceValidation] = useState(false) // Track if user modified input after validation
  const validationAbortControllerRef = useRef<AbortController | null>(null)
  const pendingValidationInputRef = useRef<string>('') // Store input being validated for cancel restoration
  const isRestoringFromCancelRef = useRef<boolean>(false) // Track when restoring input after cancel
  const lastValidatedInputRef = useRef<string>('') // Store the last validated input for content comparison
  const chatEndRef = useRef<HTMLDivElement>(null)
  
  // Project name validation states
  const [projectNameExists, setProjectNameExists] = useState(false)
  const [projectNameCheckLoading, setProjectNameCheckLoading] = useState(false)
  const [projectNameError, setProjectNameError] = useState('')
  
  const navigate = useNavigate()
  const username = localStorage.getItem('username') || 'User'

  // Auto-scroll to bottom when new content appears (append-only flow)
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [validationConversation, validationLoading, validationSuggestions, validationPassed])

  // Check if project name exists
  const checkProjectExists = async (name: string) => {
    if (!name.trim()) {
      setProjectNameExists(false)
      setProjectNameError('')
      return
    }

    setProjectNameCheckLoading(true)
    setProjectNameError('')
    
    try {
      const username = localStorage.getItem('username')

      if (!username) {
        setProjectNameError('Authentication required')
        return
      }

      const response = await authenticatedFetch(`${API_BASE}/check-project-exists/${username}/${encodeURIComponent(name)}`)

      const data = await response.json()
      
      if (data.success) {
        setProjectNameExists(data.exists)
        if (data.exists) {
          setProjectNameError(`Project "${name}" already exists`)
        }
      } else {
        setProjectNameError(data.message || 'Error checking project name')
      }
    } catch (error) {
      console.error('Error checking project name:', error)
      setProjectNameError('Network error while checking project name')
    } finally {
      setProjectNameCheckLoading(false)
    }
  }


  // Get the description that will be sent to AI generation (enhanced version with assumptions if available)
  const getEnhancedDescription = () => {
    return enhancedDescription || description
  }

  // State for copy feedback
  const [copyStatus, setCopyStatus] = useState('')
  
  // Ref for auto-resizing textarea
  const textareaRef = useRef(null)
  
  // Auto-resize textarea based on content
  const autoResizeTextarea = () => {
    const textarea = textareaRef.current
    if (textarea) {
      // Reset height to auto to get the actual content height
      textarea.style.height = 'auto'
      // Set height to scrollHeight, but maintain minimum height of 8 rows (~120px)
      const minHeight = 120 // Matches current minHeight
      textarea.style.height = Math.max(textarea.scrollHeight, minHeight) + 'px'
    }
  }

  // Auto-resize textarea when description changes from other sources
  useEffect(() => {
    autoResizeTextarea()
  }, [description])

  const copyToClipboard = async (text) => {
    try {
      // First try modern clipboard API (requires HTTPS)
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text)
        return true
      }
      
      // Fallback for non-HTTPS environments (like EC2 HTTP deployments)
      const textArea = document.createElement('textarea')
      textArea.value = text
      textArea.style.position = 'fixed'
      textArea.style.left = '-999999px'
      textArea.style.top = '-999999px'
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()
      
      const successful = document.execCommand('copy')
      document.body.removeChild(textArea)
      
      if (successful) {
        return true
      } else {
        throw new Error('document.execCommand failed')
      }
    } catch (err) {
      console.error('All copy methods failed:', err)
      console.error('Environment details:', {
        hasClipboard: !!navigator.clipboard,
        isSecureContext: window.isSecureContext,
        protocol: window.location.protocol,
        hostname: window.location.hostname
      })
      return false
    }
  }

  const copyEnhancedDescription = async () => {
    const success = await copyToClipboard(getEnhancedDescription())
    if (success) {
      setCopyStatus('✅ Copied!')
      setTimeout(() => setCopyStatus(''), 2000)
    } else {
      setCopyStatus('❌ Copy failed')
      setTimeout(() => setCopyStatus(''), 3000)
    }
  }

  const handleLogout = async () => {
    try {
      await authenticatedFetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
      })
    } catch (error) {
      console.error('Error during logout:', error)
    } finally {
      localStorage.removeItem('username')
      navigate('/', { replace: true })
    }
  }


  // Debounced project name validation
  useEffect(() => {
    if (projectName.trim()) {
      const timeoutId = setTimeout(() => {
        // Use shared validation function (pass empty array since uniqueness is checked by backend)
        const error = validateProjectName(projectName, [])

        if (error) {
          // Validation failed - show error
          setProjectNameError(error)
          setProjectNameExists(false)
        } else {
          // Validation passed - check with backend if project exists
          setProjectNameError('')
          checkProjectExists(projectName.trim())
        }
      }, 500) // 500ms debounce

      return () => clearTimeout(timeoutId)
    } else {
      setProjectNameExists(false)
      setProjectNameError('')
    }
  }, [projectName])

  
  // Clear validation session and start fresh
  const clearValidationSession = async () => {
    try {
      await authenticatedFetch(`${API_BASE}/validation-session/${projectName}`, {
        method: 'DELETE',
      })

      // Clear description input
      setDescription('')

      // Reset validation state
      setValidationSessionActive(false)
      setValidationPassed(false)
      setValidationAttempted(false)
      setValidationSuggestions([])
      setValidationAssumptions('')
      setValidationSuccessMessage('')
      setEnhancedDescription('')
      setErrors([]) // Clear any previous errors

      // Clear conversation history
      setValidationConversation([])
      setCurrentInput('')
      setInputModifiedSinceValidation(false)
      lastValidatedInputRef.current = '' // Clear the comparison reference
    } catch (error) {
      console.error('Error clearing validation session:', error)
    }
  }

  // Simplified validation function
  const cancelValidation = () => {
    if (validationAbortControllerRef.current) {
      validationAbortControllerRef.current.abort()
      validationAbortControllerRef.current = null
    }
    // Remove the last user message that was added when validation started
    setValidationConversation(prev => {
      if (prev.length > 0 && prev[prev.length - 1].role === 'user') {
        return prev.slice(0, -1)
      }
      return prev
    })
    // Restore the input that was being validated
    if (pendingValidationInputRef.current) {
      // Mark that we're restoring from cancel to preserve assumptions
      isRestoringFromCancelRef.current = true
      // If this was the first validation (no conversation before), restore to main description
      if (validationConversation.length <= 1) {
        setDescription(pendingValidationInputRef.current)
      } else {
        // Otherwise restore to the currentInput field
        setCurrentInput(pendingValidationInputRef.current)
      }
      pendingValidationInputRef.current = ''
      // Clear lastValidatedInputRef so button shows "Submit" (validation was cancelled, not completed)
      lastValidatedInputRef.current = ''
      // Ensure button shows "Submit" after cancel
      setInputModifiedSinceValidation(true)
      // Reset the flag after a tick to allow the onChange to complete
      setTimeout(() => { isRestoringFromCancelRef.current = false }, 0)
    }
    setValidationLoading(false)
  }

  const validateDescription = async () => {
    const inputToSend = validationConversation.length === 0 ? description.trim() : currentInput.trim()
    if (!inputToSend) return

    // Store input for potential cancel restoration
    pendingValidationInputRef.current = inputToSend
    // Store the validated input for content comparison (to detect if user changes it back)
    lastValidatedInputRef.current = inputToSend

    // Capture only the last assistant message for API context (all validator needs)
    const lastAssistantMsg = [...validationConversation].reverse().find(msg => msg.role === 'assistant')
    const historyForApi = lastAssistantMsg ? [{ role: lastAssistantMsg.role, content: lastAssistantMsg.content }] : []

    // Create new AbortController for this request
    validationAbortControllerRef.current = new AbortController()

    // Add user message to conversation
    const userMessage: ValidationMessage = {
      role: 'user',
      content: inputToSend,
      timestamp: Date.now()
    }
    setValidationConversation(prev => [...prev, userMessage])
    setInputModifiedSinceValidation(false) // Reset modification flag when submitting
    setCurrentInput('') // Clear input immediately while loading

    setValidationLoading(true)
    // Don't clear suggestions, assumptions, or enhanced description here
    // They will be updated when new response arrives, keeping them visible during loading
    setValidationPassed(false)
    setValidationAttempted(true)
    setValidationSuccessMessage('')
    // Mark session as active (will be cleared on successful completion)
    if (!validationSessionActive) {
      setValidationSessionActive(true)
    }

    try {
      const username = localStorage.getItem('username')

      if (!username) {
        return
      }

      const response = await authenticatedFetch(`${API_BASE}/validate-description-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_name: projectName,
          description: inputToSend,  // Use the input we're sending, not the original description
          conversation_history: historyForApi.length > 0 ? historyForApi : undefined  // Include prior conversation for context
        }),
        signal: validationAbortControllerRef.current?.signal
      })

      if (!response.ok) {
        setValidationLoading(false)
        return
      }

      // Handle streaming validation response
      const reader = response.body?.getReader()
      if (!reader) {
        setValidationLoading(false)
        return
      }

      let sseBuffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        sseBuffer += new TextDecoder().decode(value)
        const lines = sseBuffer.split('\n')
        sseBuffer = lines.pop() || '' // Keep incomplete last line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim()
            if (data === '[DONE]') {
              setValidationLoading(false)
              setValidationProgressMessage('')
              return
            }

            try {
              const parsed = JSON.parse(data)

              if (parsed.type === 'log' && parsed.message) {
                // Log messages are for progress display only
                const message = parsed.message.trim()
                if (message && message.length > 5) {
                  setValidationProgressMessage(message)
                }
              } else if (parsed.type === 'complete' || parsed.type === 'continue') {
                // Use agent_response from the event payload
                let fullResponse = parsed.agent_response || ''
                const hasValidationComplete = fullResponse.includes('VALIDATION COMPLETE')

                // Clean up response: strip everything before "ASSUMPTIONS" heading to remove analysis tags
                const assumptionsHeadingPattern = 'ASSUMPTIONS (we will use these unless you specify otherwise):'
                const assumptionsHeadingIndex = fullResponse.indexOf(assumptionsHeadingPattern)
                if (assumptionsHeadingIndex >= 0) {
                  fullResponse = fullResponse.substring(assumptionsHeadingIndex)
                }

                // Extract assumptions (only present in passed responses)
                const assumptionsMatch = fullResponse.match(/ASSUMPTIONS[^:]*:(.*?)(?=ENHANCED DESCRIPTION|VALIDATION COMPLETE|$)/s)
                let assumptions = assumptionsMatch ? assumptionsMatch[1].trim() : ''
                assumptions = fixNestedListIndentation(assumptions)
                setValidationAssumptions(assumptions)

                // Look for enhanced description - prefer from event payload
                const enhancedFromEvent = parsed.enhanced_description
                const enhancedStartIndex = fullResponse.indexOf('ENHANCED DESCRIPTION:')
                const validationCompleteIndex = fullResponse.indexOf('VALIDATION COMPLETE')

                if (enhancedFromEvent) {
                  setEnhancedDescription(enhancedFromEvent)
                } else if (enhancedStartIndex !== -1 && validationCompleteIndex !== -1) {
                  const enhancedSection = fullResponse.substring(enhancedStartIndex + 'ENHANCED DESCRIPTION:'.length, validationCompleteIndex).trim()
                  setEnhancedDescription(enhancedSection)
                } else if (!hasValidationComplete) {
                  setEnhancedDescription('')
                }

                setValidationLoading(false)

                const assistantMessage: ValidationMessage = {
                  role: 'assistant',
                  content: fullResponse,
                  timestamp: Date.now()
                }
                setValidationConversation(prev => [...prev, assistantMessage])

                if (hasValidationComplete) {
                  setValidationPassed(true)
                  setValidationSuccessMessage(fullResponse)
                  setValidationSuggestions([fullResponse])
                  setValidationSessionActive(false)

                  const finalDesc = enhancedFromEvent
                    || (enhancedStartIndex !== -1 && validationCompleteIndex !== -1
                      ? fullResponse.substring(enhancedStartIndex + 'ENHANCED DESCRIPTION:'.length, validationCompleteIndex).trim()
                      : inputToSend)
                  saveProjectOnValidationSuccess(finalDesc)
                } else {
                  // Strip <analysis>...</analysis> block to get user-facing content
                  let feedbackText = fullResponse
                  const analysisCloseIdx = feedbackText.indexOf('</analysis>')
                  if (analysisCloseIdx >= 0) {
                    feedbackText = feedbackText.substring(analysisCloseIdx + '</analysis>'.length).trim()
                  }
                  const feedbackMarkerIndex = feedbackText.indexOf('USER_FEEDBACK:')
                  let userFeedback = feedbackMarkerIndex >= 0
                    ? feedbackText.substring(feedbackMarkerIndex + 'USER_FEEDBACK:'.length).trim()
                    : feedbackText
                  userFeedback = fixNestedListIndentation(userFeedback)
                  setValidationPassed(false)
                  setValidationSuggestions([userFeedback])
                  setValidationSuccessMessage('')
                  setEnhancedDescription('')
                  setCurrentInput(inputToSend)
                }
                setValidationProgressMessage('')
                return
              } else if (parsed.type === 'error') {
                console.error('Validation error:', parsed.message)
                setValidationLoading(false)
                return
              }
            } catch (e) {
              console.error('Error parsing validation response:', e)
            }
          }
        }
      }
    } catch (error) {
      // Don't log abort errors - they're intentional cancellations
      if (error instanceof Error && error.name === 'AbortError') {
        // User cancelled - just stop loading
        setValidationLoading(false)
        return
      }
      console.error('Validation error:', error)
      setValidationLoading(false)
    }
  }

  const handleValidateOnly = async () => {
    setErrors([])

    // Frontend validation
    const validationErrors = []
    if (!projectName.trim()) {
      validationErrors.push('Project name is required')
    }
    if (!description.trim()) {
      validationErrors.push('Project description is required')
    }
    if (projectName.trim().length > 255) {
      validationErrors.push('Project name must be 255 characters or less')
    }
    // New validations: no spaces, no capital letters, no hyphens, cannot begin with number
    if (projectName.trim()) {
      if (/\s/.test(projectName)) {
        validationErrors.push('Project name cannot contain spaces')
      }
      if (/[A-Z]/.test(projectName)) {
        validationErrors.push('Project name cannot contain capital letters')
      }
      if (/^[0-9]/.test(projectName)) {
        validationErrors.push('Project name cannot begin with a number')
      }
      if (!/^[a-z_][a-z0-9_]*$/.test(projectName)) {
        validationErrors.push('Project name can only contain lowercase letters, numbers, and underscores')
      }
    }

    if (validationErrors.length > 0) {
      setErrors(validationErrors)
      return
    }

    // Run AI validation
    await validateDescription()
  }

  // Save project when validation passes (so it shows in connector list)
  const saveProjectOnValidationSuccess = async (finalDescription: string) => {
    try {
      const username = localStorage.getItem('username')
      if (!username || !projectName.trim()) {
        console.error('Cannot save project: missing username or project name')
        return false
      }

      const createResponse = await authenticatedFetch(`${API_BASE}/create-project`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username,
          project_name: projectName,
          description: finalDescription,
        }),
      })

      const createData = await createResponse.json()
      if (createData.success) {
        // Store project info for navigation
        localStorage.setItem('current_project_name', createData.project_name)
        localStorage.setItem('current_project_description', finalDescription)
        return true
      } else {
        // Project might already exist (409 conflict) - that's ok
        if (createResponse.status === 409) {
          console.log('Project already exists, will use existing')
          localStorage.setItem('current_project_name', projectName)
          localStorage.setItem('current_project_description', finalDescription)
          return true
        }
        console.error('Failed to save project:', createData.message)
        return false
      }
    } catch (error) {
      console.error('Error saving project on validation success:', error)
      return false
    }
  }

  const handleProceedToGeneration = async () => {
    // Project was already saved when validation passed - navigate to AI builder
    // AIBuilderPage will check if connector.py exists and generate if needed
    localStorage.setItem('current_project_name', projectName)
    navigate('/ai-builder')
  }

  const handleNext = async () => {
    return handleProceedToGeneration()
  }

  const handleOverrideAndCreate = async () => {
    setLoading(true)
    setErrors([])
    setGenerationStatus('')

    // Use currentInput if in validation conversation, otherwise use description
    // If currentInput is empty but we have conversation history, use the last user message
    let descriptionToUse = description.trim()
    if (validationConversation.length > 0) {
      if (currentInput.trim()) {
        descriptionToUse = currentInput.trim()
      } else {
        // Fallback: get the last user message from the conversation
        const lastUserMessage = [...validationConversation].reverse().find(m => m.role === 'user')
        if (lastUserMessage) {
          descriptionToUse = lastUserMessage.content
        }
      }
    }

    // Frontend validation
    const validationErrors = []
    if (!projectName.trim()) {
      validationErrors.push('Project name is required')
    }
    if (!descriptionToUse) {
      validationErrors.push('Project description is required')
    }
    if (projectName.trim().length > 255) {
      validationErrors.push('Project name must be 255 characters or less')
    }
    // New validations: no spaces, no capital letters, no hyphens, cannot begin with number
    if (projectName.trim()) {
      if (/\s/.test(projectName)) {
        validationErrors.push('Project name cannot contain spaces')
      }
      if (/[A-Z]/.test(projectName)) {
        validationErrors.push('Project name cannot contain capital letters')
      }
      if (/^[0-9]/.test(projectName)) {
        validationErrors.push('Project name cannot begin with a number')
      }
      if (!/^[a-z_][a-z0-9_]*$/.test(projectName)) {
        validationErrors.push('Project name can only contain lowercase letters, numbers, and underscores')
      }
    }

    if (validationErrors.length > 0) {
      setErrors(validationErrors)
      setLoading(false)
      return
    }

    try {
      const username = localStorage.getItem('username')
      if (!username) {
        alert('Please login first')
        return
      }

      // Create new project

      // Step 1: Create project (validation)
      // OVERRIDE: Use only original description (not enhanced)
      const finalDescriptionForGeneration = descriptionToUse
      const createResponse = await authenticatedFetch(`${API_BASE}/create-project`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username,
          project_name: projectName,
          description: finalDescriptionForGeneration,
        }),
      })

      const createData = await createResponse.json()
      if (!createData.success) {
        // Show validation errors (401 handled globally by authenticatedFetch)
        if (createData.errors && Array.isArray(createData.errors)) {
          setErrors(createData.errors)
        } else {
          setErrors([createData.message || 'Failed to create project'])
        }
        return
      }

      // Store project info and navigate to AI Builder
      // AI builder will check if connector.py exists and generate if needed
      localStorage.setItem('current_project_name', createData.project_name)
      // Reset validation states for next time
      setProjectNameExists(false)
      setProjectNameError('')
      navigate('/ai-builder')
    } catch (error) {
      console.error('Error creating project:', error)
      setErrors(['Error creating project. Please try again.'])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-fade-in" style={{ 
      height: '100vh', 
      background: '#1B1818',
      color: '#FDFCFB',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      position: 'relative'
    }}>
      {/* Gradient overlay */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          right: 0,
          bottom: 0,
          left: 0,
          background:
            'radial-gradient(ellipse 77% 51% at 50% 130%, rgba(48,107,234,0.5) 0%, rgba(48,107,234,0) 80%), ' +
            'radial-gradient(ellipse 103% 70% at 50% 130%, rgba(48,107,234,0.3) 0%, rgba(48,107,234,0) 100%), ' +
            'radial-gradient(ellipse 112% 73% at 50% 130%, rgba(48,107,234,0.25) 0%, rgba(48,107,234,0) 100%)',
          zIndex: 0,
        }}
      />
      {/* Header */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        padding: '12px 40px',
        borderBottom: '1px solid #333',
        flexShrink: 0,
        position: 'relative',
        zIndex: 1
      }}>
        {/* Top row: Logo + App Name | Logout */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <img
              src="/fivetran-mark-white-rgb.png"
              alt="Fivetran"
              style={{
                height: '32px',
                filter: 'brightness(0.9)'
              }}
            />
            <h1 style={{ margin: 0, fontSize: '20px' }}>{APP_NAME} <span style={{ fontSize: '12px', color: '#9b948f', fontWeight: 'normal' }}>(v{APP_VERSION})</span></h1>
          </div>
          {/* Username + Logout Button */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ color: '#9b948f', fontSize: '14px' }}>{username}</span>
            <button
              onClick={handleLogout}
              style={{
                padding: '8px 16px',
                background: 'rgba(255, 255, 255, 0.1)',
                color: '#FDFCFB',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '14px',
                transition: 'all 0.2s ease'
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.2)'
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'
              }}
            >
              Logout
            </button>
          </div>
        </div>
        {/* Second row: Back arrow + Page title */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button
            onClick={() => navigate('/')}
            style={{
              background: 'transparent',
              border: '1px solid #444',
              borderRadius: '4px',
              color: '#9b948f',
              fontSize: '16px',
              cursor: 'pointer',
              padding: '4px 10px',
              display: 'flex',
              alignItems: 'center',
              transition: 'all 0.2s ease'
            }}
            onMouseOver={(e) => { e.currentTarget.style.color = '#FDFCFB'; e.currentTarget.style.borderColor = '#666' }}
            onMouseOut={(e) => { e.currentTarget.style.color = '#9b948f'; e.currentTarget.style.borderColor = '#444' }}
            title="Home"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
              <polyline points="9 22 9 12 15 12 15 22"></polyline>
            </svg>
          </button>
          <span style={{ fontSize: '16px', color: '#FDFCFB' }}>Planning</span>
        </div>
      </div>

      {/* Main Content - Two Columns */}
      <div style={{ 
        display: 'flex', 
        flex: 1,
        gap: '2px',
        padding: '20px',
        background: 'transparent',
        minHeight: 0,
        position: 'relative',
        zIndex: 1
      }}>
        {/* Left Column - Form */}
        <div style={{ 
          flex: 1, 
          background: 'rgba(26, 26, 26, 0.8)', 
          padding: '40px', 
          backdropFilter: 'blur(10px)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          overflow: 'auto',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', color: '#FDFCFB' }}>
                What do you want to call this project?
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="Enter your project name here..."
                  style={{
                    width: '100%',
                    padding: '12px',
                    paddingRight: projectNameCheckLoading ? '40px' : '12px',
                    background: '#2a2a2a',
                    border: `1px solid ${projectNameError ? '#e74c3c' : projectNameExists ? '#e74c3c' : projectName && !projectNameError && !projectNameExists ? '#27ae60' : '#444'}`,
                    borderRadius: '6px',
                    color: '#FDFCFB',
                    fontSize: '14px',
                    boxSizing: 'border-box',
                  }}
                />
                {projectNameCheckLoading && (
                  <div style={{
                    position: 'absolute',
                    right: '12px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: '16px',
                    height: '16px',
                    border: '2px solid #666',
                    borderTop: '2px solid #306BEA',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite'
                  }} />
                )}
                {!projectNameCheckLoading && projectName && !projectNameError && !projectNameExists && (
                  <div style={{
                    position: 'absolute',
                    right: '12px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    color: '#27ae60',
                    fontSize: '16px'
                  }}>✓</div>
                )}
                {!projectNameCheckLoading && projectNameError && (
                  <div style={{
                    position: 'absolute',
                    right: '12px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    color: '#e74c3c',
                    fontSize: '16px'
                  }}>⚠</div>
                )}
              </div>
              {projectNameError && (
                <div style={{ 
                  color: '#e74c3c', 
                  fontSize: '12px', 
                  marginTop: '4px'
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    marginBottom: '4px'
                  }}>
                    ⚠ {projectNameError}
                  </div>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <label style={{ display: 'block', marginBottom: '4px', fontSize: '14px', color: '#FDFCFB' }}>
                Describe the connector you want to build
              </label>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                marginBottom: '8px',
              }}>
                <span style={{ fontSize: '12px', lineHeight: '1' }}>ℹ️</span>
                <span style={{ fontSize: '12px', color: '#9b948f' }}>
                  I'll provide feedback on your description if necessary.
                </span>
              </div>

              {/* Stacked conversation - each exchange shows input (read-only) then response */}
              <div style={{
                flex: -1,
                display: 'flex',
                flexDirection: 'column',
                gap: '10px',
                marginBottom: '8px',
                overflowX: 'hidden',
              }}>
                {validationConversation.length === 0 ? (
                  <textarea
                    ref={textareaRef}
                    value={description}
                    onChange={(e) => {
                      setDescription(e.target.value)
                      // Reset validation states when description changes (but not during cancel restoration)
                      setValidationPassed(false)
                      setValidationAttempted(false)
                      setValidationSuccessMessage('')
                      if (!isRestoringFromCancelRef.current) {
                        setValidationAssumptions('')
                      }
                      // Auto-resize textarea after content change
                      setTimeout(autoResizeTextarea, 0)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault()
                        validateDescription()
                      }
                    }}
                    placeholder="Enter information about your data source here... (⌘/Ctrl+Enter to submit)"
                    rows={8}
                    style={{
                      width: '100%',
                      padding: '14px',
                      background: '#2a2a2a',
                      border: '2px solid #444',
                      borderRadius: '8px',
                      color: '#FDFCFB',
                      fontSize: '14px',
                      lineHeight: '1.6',
                      resize: 'vertical',
                      minHeight: '120px',
                      maxHeight: '300px',
                      overflowY: 'scroll',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                      transition: 'border-color 0.2s ease',
                      boxSizing: 'border-box',
                    }}
                    onFocus={(e) => e.currentTarget.style.borderColor = '#306BEA'}
                    onBlur={(e) => e.currentTarget.style.borderColor = '#444'}
                  />
                ) : (
                  <>
                    {/* Render ALL messages from validationConversation in chronological order */}
                    {(() => {
                      // Group messages into pairs: [user, assistant?]
                      const userMessages = validationConversation.filter(m => m.role === 'user')
                      const assistantMessages = validationConversation.filter(m => m.role === 'assistant')

                      return userMessages.map((userMsg, userIndex) => {
                        const correspondingAssistant = assistantMessages[userIndex]
                        const isLastPair = userIndex === userMessages.length - 1

                        return (
                          <div key={`pair-${userIndex}`}>
                            {/* User message */}
                            <div style={{
                              position: 'relative',
                              animation: 'fadeIn 0.3s ease-in',
                              marginBottom: correspondingAssistant ? '16px' : '0'
                            }}>
                              <textarea
                                value={userMsg.content}
                                readOnly
                                style={{
                                  width: '100%',
                                  padding: '14px',
                                  paddingLeft: '40px',
                                  background: 'linear-gradient(135deg, #2a2a2a 0%, #252525 100%)',
                                  border: '1px solid #3a3a3a',
                                  borderRadius: '8px',
                                  color: '#FDFCFB',
                                  fontSize: '14px',
                                  lineHeight: '1.6',
                                  resize: 'none',
                                  cursor: 'default',
                                  opacity: 0.85,
                                  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                                  boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                                  boxSizing: 'border-box',
                                  minHeight: '120px',
                                  overflow: 'hidden',
                                  height: 'auto',
                                  fieldSizing: 'content',
                                } as React.CSSProperties}
                              />
                              <div style={{
                                position: 'absolute',
                                left: '14px',
                                top: '14px',
                                width: '20px',
                                height: '20px',
                                borderRadius: '50%',
                                background: 'linear-gradient(135deg, #306BEA 0%, #2557C9 100%)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                fontSize: '10px',
                                color: 'white',
                                fontWeight: 'bold',
                                boxShadow: '0 2px 4px rgba(48, 107, 234, 0.3)',
                              }}>
                                {userIndex + 1}
                              </div>
                            </div>

                            {/* Corresponding AI feedback */}
                            {correspondingAssistant && !validationPassed && (() => {
                              let feedback = correspondingAssistant.content || ''
                              // Strip <analysis>...</analysis> block entirely if present
                              const analysisEndIndex = feedback.indexOf('</analysis>')
                              if (analysisEndIndex >= 0) {
                                feedback = feedback.substring(analysisEndIndex + '</analysis>'.length).trim()
                              } else {
                                feedback = feedback.replace(/^<analysis>\s*/s, '')
                              }
                              feedback = feedback.replace(/<\/?analysis>/g, '')
                              const feedbackMarkerIndex = feedback.indexOf('USER_FEEDBACK:')
                              if (feedbackMarkerIndex >= 0) {
                                feedback = feedback.substring(feedbackMarkerIndex + 'USER_FEEDBACK:'.length).trim()
                              }
                              feedback = feedback.replace(/([^\n])\n(\*\*[^*]+\*\*)/g, '$1\n\n$2')

                              return (
                                <div className="content-fade-in" style={{
                                  padding: '12px',
                                  background: '#1a3a4a',
                                  border: '1px solid #306BEA',
                                  borderRadius: '6px',
                                  marginBottom: isLastPair ? '16px' : '20px',
                                  flexShrink: 0
                                }}>
                                  <div style={{ fontSize: '14px', lineHeight: '1.7' }}>
                                    <ReactMarkdown
                                      components={{
                                        p: ({node, ...props}) => <div style={{ color: '#FDFCFB', margin: '0 0 10px 0' }} {...props} />,
                                        strong: ({node, ...props}) => <strong style={{ color: '#FDFCFB', fontWeight: 'bold' }} {...props} />,
                                        li: ({node, ...props}) => <li style={{ color: '#FDFCFB', marginBottom: '6px', listStylePosition: 'outside' }} {...props} />,
                                        ul: ({node, ...props}) => <ul style={{ color: '#FDFCFB', margin: '6px 0', paddingLeft: '28px', listStyleType: 'disc' }} {...props} />,
                                        ol: ({node, ...props}) => <ol style={{ color: '#FDFCFB', margin: '6px 0', paddingLeft: '28px', listStyleType: 'decimal' }} {...props} />,
                                        h2: ({node, ...props}) => <div style={{ color: '#FDFCFB', fontSize: '16px', fontWeight: 'bold', margin: '14px 0 8px 0' }} {...props} />,
                                        h3: ({node, ...props}) => <div style={{ color: '#FDFCFB', fontSize: '15px', fontWeight: 'bold', margin: '12px 0 6px 0' }} {...props} />,
                                        code: ({node, ...props}) => <code style={{ color: '#FDFCFB', backgroundColor: 'rgba(255, 255, 255, 0.1)', padding: '2px 4px', borderRadius: '3px', fontSize: '13px' }} {...props} />
                                      }}
                                    >
                                      {feedback}
                                    </ReactMarkdown>
                                  </div>
                                  {isLastPair && (
                                    <div style={{ fontSize: '13px', color: '#9b948f', marginTop: '10px', fontStyle: 'italic' }}>
                                      Update your description below and click Submit.
                                    </div>
                                  )}
                                </div>
                              )
                            })()}
                          </div>
                        )
                      })
                    })()}
                  </>
                )}
              </div>
            </div>

            {/* Error Display */}
            {errors.length > 0 && (
              <div style={{
                padding: '12px',
                background: '#4a1a1a',
                border: '1px solid #ff6b6b',
                borderRadius: '6px',
                marginBottom: '16px',
                flexShrink: 0
              }}>
                <div style={{ color: '#ff6b6b', fontSize: '14px', fontWeight: 'bold', marginBottom: '8px' }}>
                  Validation Errors:
                </div>
                {errors.map((error, index) => (
                  <div key={index} style={{ color: '#ff6b6b', fontSize: '12px', marginBottom: '4px' }}>
                    • {error}
                  </div>
                ))}
              </div>
            )}

            {/* New input box and action buttons - show after validation feedback when not passed and not loading */}
            {validationConversation.length > 0 && !validationPassed && !validationLoading && (
              <>
                {/* Input box for next message */}
                <div style={{ position: 'relative', marginBottom: '12px' }}>
                  <textarea
                    value={currentInput}
                    onChange={(e) => {
                      setCurrentInput(e.target.value)
                      // Compare content to last validated input - if same, not modified
                      setInputModifiedSinceValidation(e.target.value.trim() !== lastValidatedInputRef.current)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault()
                        validateDescription()
                      }
                    }}
                    placeholder="Update your description here... (⌘/Ctrl+Enter to submit)"
                    rows={8}
                    style={{
                      width: '100%',
                      padding: '14px',
                      background: '#2a2a2a',
                      border: '2px solid #306BEA',
                      borderRadius: '8px',
                      color: '#FDFCFB',
                      fontSize: '14px',
                      lineHeight: '1.6',
                      resize: 'vertical',
                      minHeight: '120px',
                      maxHeight: '300px',
                      overflowY: 'scroll',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                      transition: 'all 0.2s ease',
                      boxShadow: '0 0 0 3px rgba(48, 107, 234, 0.1)',
                      boxSizing: 'border-box',
                    }}
                    onFocus={(e) => {
                      e.currentTarget.style.boxShadow = '0 0 0 4px rgba(48, 107, 234, 0.2)'
                    }}
                    onBlur={(e) => {
                      e.currentTarget.style.boxShadow = '0 0 0 3px rgba(48, 107, 234, 0.1)'
                    }}
                  />
                </div>

                {/* Action buttons */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', gap: '12px' }}>
                  <button
                    onClick={clearValidationSession}
                    style={{
                      padding: '10px 18px',
                      background: 'linear-gradient(135deg, #555 0%, #444 100%)',
                      color: '#FDFCFB',
                      border: '1px solid #666',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontSize: '13px',
                      fontWeight: '500',
                      transition: 'all 0.2s ease',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                    }}
                    onMouseOver={(e) => {
                      e.currentTarget.style.background = 'linear-gradient(135deg, #666 0%, #555 100%)'
                      e.currentTarget.style.transform = 'translateY(-1px)'
                      e.currentTarget.style.boxShadow = '0 4px 8px rgba(0,0,0,0.3)'
                    }}
                    onMouseOut={(e) => {
                      e.currentTarget.style.background = 'linear-gradient(135deg, #555 0%, #444 100%)'
                      e.currentTarget.style.transform = 'translateY(0)'
                      e.currentTarget.style.boxShadow = '0 2px 4px rgba(0,0,0,0.2)'
                    }}
                  >
                    Clear
                  </button>

                  <button
                    onClick={!inputModifiedSinceValidation ? handleOverrideAndCreate : handleValidateOnly}
                    disabled={loading}
                    style={{
                      padding: '10px 20px',
                      background: loading
                        ? '#666'
                        : !inputModifiedSinceValidation
                          ? 'linear-gradient(135deg, #e67e22 0%, #d35400 100%)'
                          : 'linear-gradient(135deg, #306BEA 0%, #2557C9 100%)',
                      color: '#FDFCFB',
                      border: !inputModifiedSinceValidation
                        ? '1px solid #e67e22'
                        : '1px solid #306BEA',
                      borderRadius: '6px',
                      cursor: loading ? 'not-allowed' : 'pointer',
                      fontSize: '13px',
                      fontWeight: '600',
                      transition: 'all 0.2s ease',
                      boxShadow: !inputModifiedSinceValidation
                        ? '0 2px 8px rgba(230, 126, 34, 0.3)'
                        : '0 2px 8px rgba(48, 107, 234, 0.3)',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                    }}
                    onMouseOver={(e) => {
                      if (!inputModifiedSinceValidation) {
                        e.currentTarget.style.background = 'linear-gradient(135deg, #d35400 0%, #c0392b 100%)'
                        e.currentTarget.style.boxShadow = '0 4px 12px rgba(230, 126, 34, 0.4)'
                      } else {
                        e.currentTarget.style.background = 'linear-gradient(135deg, #2557C9 0%, #1d4ba8 100%)'
                        e.currentTarget.style.boxShadow = '0 4px 12px rgba(48, 107, 234, 0.4)'
                      }
                      e.currentTarget.style.transform = 'translateY(-1px)'
                    }}
                    onMouseOut={(e) => {
                      if (!inputModifiedSinceValidation) {
                        e.currentTarget.style.background = 'linear-gradient(135deg, #e67e22 0%, #d35400 100%)'
                        e.currentTarget.style.boxShadow = '0 2px 8px rgba(230, 126, 34, 0.3)'
                      } else {
                        e.currentTarget.style.background = 'linear-gradient(135deg, #306BEA 0%, #2557C9 100%)'
                        e.currentTarget.style.boxShadow = '0 2px 8px rgba(48, 107, 234, 0.3)'
                      }
                      e.currentTarget.style.transform = 'translateY(0)'
                    }}
                  >
                    {!inputModifiedSinceValidation ? 'Ignore & Continue' : 'Submit'}
                  </button>
                </div>
              </>
            )}

            {/* Validation Loading Indicator - at the bottom for append-only flow */}
            {validationLoading && (
              <div className="content-fade-in" style={{
                padding: '12px',
                background: 'rgba(48, 107, 234, 0.1)',
                border: '1px solid rgba(48, 107, 234, 0.3)',
                borderRadius: '6px',
                marginBottom: '16px',
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '12px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{
                    display: 'flex',
                    gap: '4px'
                  }}>
                    <div style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      backgroundColor: '#306BEA',
                      animation: 'typing 1.4s infinite ease-in-out'
                    }}></div>
                    <div style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      backgroundColor: '#306BEA',
                      animation: 'typing 1.4s infinite ease-in-out 0.2s'
                    }}></div>
                    <div style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      backgroundColor: '#306BEA',
                      animation: 'typing 1.4s infinite ease-in-out 0.4s'
                    }}></div>
                  </div>
                  <span style={{ color: '#306BEA', fontSize: '13px', fontWeight: '500' }}>
                    {validationProgressMessage || 'AI is analyzing the connector description...'}
                  </span>
                </div>
                <button
                  onClick={cancelValidation}
                  style={{
                    padding: '4px 12px',
                    background: 'transparent',
                    color: '#e74c3c',
                    border: '1px solid #e74c3c',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '12px',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseOver={(e) => {
                    e.currentTarget.style.background = 'rgba(231, 76, 60, 0.1)'
                    e.currentTarget.style.borderColor = '#c0392b'
                  }}
                  onMouseOut={(e) => {
                    e.currentTarget.style.background = 'transparent'
                    e.currentTarget.style.borderColor = '#e74c3c'
                  }}
                >
                  Cancel
                </button>
              </div>
            )}

            {/* Validation Success Display - at the bottom for append-only flow */}
            {validationPassed && (
              <div className="content-fade-in" style={{
                padding: '12px',
                background: '#1a4a1a',
                border: '1px solid #4CAF50',
                borderRadius: '6px',
                marginBottom: '16px',
                flexShrink: 0
              }}>
                <div style={{ color: '#4CAF50', fontSize: '14px', fontWeight: 'bold', marginBottom: '8px' }}>
                  ✅ Project validation succeeded
                </div>
                <div style={{ color: '#FDFCFB', fontSize: '12px' }}>
                  {'You are ready to generate your connector.'}
                </div>
              </div>
            )}

            {/* Enhanced Description Viewer - Show when enhanced description exists */}
            {enhancedDescription && (
              <div className="content-fade-in" style={{ 
                padding: '12px', 
                background: '#2a2a2a', 
                border: '1px solid #444', 
                borderRadius: '6px',
                marginBottom: '16px',
                flexShrink: 0
              }}>
                <div 
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    cursor: 'pointer',
                    marginBottom: showPromptViewer ? '12px' : '0'
                  }}
                  onClick={() => setShowPromptViewer(!showPromptViewer)}
                >
                  <span style={{ 
                    fontSize: '12px',
                    transform: showPromptViewer ? 'rotate(90deg)' : 'rotate(0deg)',
                    transition: 'transform 0.2s ease',
                    marginRight: '8px'
                  }}>▶</span>
                  <span style={{ color: '#bdb7b2', fontSize: '14px', fontWeight: 'bold' }}>
                    📝 View Full Description
                  </span>
                  <span style={{ color: '#9b948f', fontSize: '12px', marginLeft: '8px', fontStyle: 'italic' }}>
                    (Click to {showPromptViewer ? 'hide' : 'show'})
                  </span>
                </div>

                {showPromptViewer && (
                  <div className="content-fade-in">
                    <div style={{ color: '#bdb7b2', fontSize: '12px', marginBottom: '8px' }}>
                      This is the enhanced description that will be used for connector generation:
                    </div>
                    <div style={{
                      background: '#1a1a1a',
                      border: '1px solid #333',
                      borderRadius: '4px',
                      padding: '12px',
                      fontSize: '13px',
                      maxHeight: '300px',
                      overflowY: 'auto',
                      lineHeight: '1.5'
                    }}>
                      <ReactMarkdown
                        components={{
                          p: ({node, ...props}) => <div style={{ color: '#FDFCFB', margin: '0 0 10px 0' }} {...props} />,
                          strong: ({node, ...props}) => <strong style={{ color: '#FDFCFB', fontWeight: 'bold' }} {...props} />,
                          li: ({node, ...props}) => <li style={{ color: '#FDFCFB', marginBottom: '6px', listStylePosition: 'outside' }} {...props} />,
                          ul: ({node, ...props}) => <ul style={{ color: '#FDFCFB', margin: '6px 0', paddingLeft: '28px', listStyleType: 'disc' }} {...props} />,
                          ol: ({node, ...props}) => <ol style={{ color: '#FDFCFB', margin: '6px 0', paddingLeft: '28px', listStyleType: 'decimal' }} {...props} />,
                          h1: ({node, ...props}) => <div style={{ color: '#FDFCFB', fontSize: '18px', fontWeight: 'bold', margin: '16px 0 8px 0' }} {...props} />,
                          h2: ({node, ...props}) => <div style={{ color: '#FDFCFB', fontSize: '16px', fontWeight: 'bold', margin: '14px 0 8px 0' }} {...props} />,
                          h3: ({node, ...props}) => <div style={{ color: '#FDFCFB', fontSize: '15px', fontWeight: 'bold', margin: '12px 0 6px 0' }} {...props} />,
                          code: ({node, ...props}) => <code style={{ color: '#FDFCFB', backgroundColor: 'rgba(255, 255, 255, 0.1)', padding: '2px 4px', borderRadius: '3px', fontSize: '13px' }} {...props} />
                        }}
                      >
                        {getEnhancedDescription()}
                      </ReactMarkdown>
                    </div>
                    <div style={{ 
                      display: 'flex', 
                      justifyContent: 'flex-end', 
                      marginTop: '8px' 
                    }}>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          copyEnhancedDescription()
                        }}
                        style={{
                          padding: '4px 12px',
                          background: '#306BEA',
                          color: '#FDFCFB',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: 'pointer',
                          fontSize: '11px'
                        }}
                      >
                        {copyStatus || '📋 Copy Enhanced Prompt'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Scroll anchor - at the very bottom for append-only flow */}
            <div ref={chatEndRef} />

<div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', flexShrink: 0 }}>
              {/* Send / Create Connector button - dual purpose */}
              {validationConversation.length > 0 && validationPassed && (
                <button
                  onClick={handleProceedToGeneration}
                  disabled={loading || validationLoading || projectNameCheckLoading || projectNameExists}
                  style={{
                    padding: '12px 24px',
                    background: (loading || validationLoading || projectNameCheckLoading || projectNameExists) ? '#666' : '#306BEA',
                    color: '#FDFCFB',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: (loading || validationLoading || projectNameCheckLoading || projectNameExists) ? 'not-allowed' : 'pointer',
                    fontSize: '14px',
                  }}
                >
                  Move to Development →
                </button>
              )}

              {/* Initial Submit button - only show when no conversation */}
              {validationConversation.length === 0 && (
                <button
                  onClick={handleValidateOnly}
                  disabled={
                    loading || validationLoading || projectNameCheckLoading || projectNameExists ||
                    (!projectName.trim()) || !description.trim()
                  }
                  style={{
                    padding: '12px 24px',
                    background: (
                      loading || validationLoading || projectNameCheckLoading || projectNameExists ||
                      (!projectName.trim()) || !description.trim()
                    ) ? '#666' : '#306BEA',
                    color: '#FDFCFB',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: (
                      loading || validationLoading || projectNameCheckLoading || projectNameExists ||
                      (!projectName.trim()) || !description.trim()
                    ) ? 'not-allowed' : 'pointer',
                    fontSize: '14px',
                  }}
                >
                  {loading ? (generationStatus || 'Creating...') :
                   validationLoading ? 'Submitting...' :
                   'Submit'}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Right Column - Instructions */}
        <div style={{ 
          flex: 1, 
          background: 'rgba(26, 26, 26, 0.8)', 
          padding: '40px', 
          backdropFilter: 'blur(10px)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          overflow: 'auto'
        }}>
          <h1 style={{ margin: '0 0 16px 0', fontSize: '18px', color: '#FDFCFB' }}>Plan your connector</h1>
          <p style={{ color: '#bdb7b2', lineHeight: '24px', fontSize: '14px' }}>
              Please gather the following information to build and test your connector. It will speed up the process, and increase the chance that the connector will meet your needs. The more information you provide, the better the outcome will be.
                <br /><br />
                <h2>The source</h2>
                <strong>Information that will help me:</strong><br />
                - <strong>Where are we getting data from?</strong><br />
                - <strong>Where can I learn about how to get that data?</strong><br />
                - <strong>Things you should share with me to help answer these include:</strong><br />
                &nbsp;&nbsp;- API documentation links or PDFs<br />
                &nbsp;&nbsp;- Authentication methods required<br />
                &nbsp;&nbsp;- Data structure details and endpoints<br />


                <h2>Authentication</h2>
                <strong>Information that will help me:</strong><br />
                - <strong>Which of the available types of authentication do you want to use</strong><br />
                - <strong>Which keys will you provide values for, eg User Name & Password, or Basic API Key or Client ID & Client Secret, or User Name, Password, Host URL, Port</strong>
                <br /><br />
                <strong>Dont enter sensitive values into this plan you’ll enter those later into the temporary file</strong><br />



                <h2>The data to sync</h2>
                <strong>Information that will help me:</strong><br />
                - <strong>Which API endpoints do you need to get data from</strong><br />
                - <strong>What tables do you want the data split into</strong><br />
                - <strong>How normalized/flattened you want the data</strong>

                <br /><br />
                <strong>Best practice is to start with one endpoint and get that verified and working before adding more.
                You can add additional endpoints and data later</strong>

                <h3>For each table we’ll need to plan </h3>
                - <strong>the table’s primary key </strong><br />
                - <strong>the sync pattern to use for the data (eg full refresh every sync, incremental or something else)</strong><br />
                - <strong>For incremental syncs we’ll need to identify a column to use as the cursor to track what data has been sync’ed already and what data is new</strong>
          </p>
        </div>
      </div>
    </div>
  )
}

type ChatMessage = {
  type: 'user' | 'ai'
  text: string
  timestamp: string
  responseTime?: number
}

function AIBuilderPage() {
  const [activeTab, setActiveTab] = useState('files')
  const [selectedFile, setSelectedFile] = useState('')
  const [chatInput, setChatInput] = useState('')
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [cancellingConfig, setCancellingConfig] = useState(false)
  const [projectName, setProjectName] = useState('Untitled Project')
  const [projectFiles, setProjectFiles] = useState<Array<{name: string, size: number, modified: string}>>([])
  const [codeContent, setCodeContent] = useState('')
  const [configDecryptFailed, setConfigDecryptFailed] = useState(false)
  const [configDecryptMessage, setConfigDecryptMessage] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [isEditing, setIsEditing] = useState(false)
  const navigate = useNavigate()
  const username = localStorage.getItem('username') || 'User'

  const handleLogout = async () => {
    try {
      await authenticatedFetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
      })
    } catch (error) {
      console.error('Error during logout:', error)
    } finally {
      localStorage.removeItem('username')
      navigate('/', { replace: true })
    }
  }
  const [leftPanelWidth, setLeftPanelWidth] = useState(32) // Default 32%
  const [isResizing, setIsResizing] = useState(false)
  const [showRightPanel, setShowRightPanel] = useState(false) // Right panel hidden by default
  const [fileExplorerWidth, setFileExplorerWidth] = useState(240) // Default 240px
  const [isResizingFileExplorer, setIsResizingFileExplorer] = useState(false)
  const [monacoEditor, setMonacoEditor] = useState<any>(null)
  const [expandedDirectories, setExpandedDirectories] = useState<{[key: string]: boolean}>({})
  const [debugLoading, setDebugLoading] = useState(false)
  const [aiFixLoading, setAiFixLoading] = useState(false)
  const [pendingAIFixLogs, setPendingAIFixLogs] = useState<string | null>(null)
  const [logs, setLogs] = useState<Array<{timestamp: string, level: string, message: string}>>([])
  const testLogsClearedRef = useRef(false)
  const [showDeployDialog, setShowDeployDialog] = useState(false)
  const [deployLoading, setDeployLoading] = useState(false)
  const [deployForm, setDeployForm] = useState({
    connectorName: '',
    destinationName: '',
    includeConfig: true,
    forceDeployment: true,
    apiKey: ''
  })
  const [showApiKey, setShowApiKey] = useState(false)
  const [deployLogs, setDeployLogs] = useState<Array<{timestamp: string, level: string, message: string}>>([])
  const [deployError, setDeployError] = useState('')
  const [deployStatus, setDeployStatus] = useState<'success' | 'failed' | 'running' | null>(null)
  const deployLogsRef = useRef<HTMLDivElement>(null)
  const [abortController, setAbortController] = useState<AbortController | null>(null)
  const [debugAbortController, setDebugAbortController] = useState<AbortController | null>(null)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [fileToDelete, setFileToDelete] = useState('')
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [showResetDialog, setShowResetDialog] = useState(false)
  const [resetLoading, setResetLoading] = useState(false)
  const [resetDeleteVenv, setResetDeleteVenv] = useState(false)
  const [filesLoading, setFilesLoading] = useState(false)
  const [showConfigReview, setShowConfigReview] = useState(false)
  const [configData, setConfigData] = useState<{[key: string]: any}>({})
  const [sensitiveFields, setSensitiveFields] = useState<Set<string>>(new Set())
  const [visibleSensitiveFields, setVisibleSensitiveFields] = useState<Set<string>>(new Set())
  const [configSubmitting, setConfigSubmitting] = useState(false)
  const [configContext, setConfigContext] = useState<'generation' | 'debug' | 'edit' | null>(null)
  const [needsGeneration, setNeedsGeneration] = useState(false)
  const [specExpanded, setSpecExpanded] = useState(false)
  const [projectDescription, setProjectDescription] = useState<string>('')

  // Debug abortController changes
  useEffect(() => {
  }, [abortController])
  
  // Session refresh function
  const refreshSession = async () => {
    try {
      const response = await authenticatedFetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      })
      
      if (response.ok) {
        const data = await response.json()
        return true
      } else {
        console.warn('Session refresh failed:', response.status)
        return false
      }
    } catch (error) {
      console.error('Error refreshing session:', error)
      return false
    }
  }
  
  // Auto-refresh session every 2 minutes
  useEffect(() => {
    const interval = setInterval(async () => {
      const success = await refreshSession()
      if (!success) {
        console.warn('Session refresh failed, user may need to re-login')
      }
    }, 2 * 60 * 1000) // 2 minutes
    
    return () => clearInterval(interval)
  }, [])
  
  // Warning before page refresh when operations are active
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      // Check if any operations are currently running
      if (loading || debugLoading || deployLoading) {
        e.preventDefault()
        e.returnValue = 'Operation in progress - refreshing will cancel it. Are you sure?'
        return 'Operation in progress - refreshing will cancel it. Are you sure?'
      }
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
    }
  }, [loading, debugLoading, deployLoading])
  
  // Load project data and chat history on component mount
  useEffect(() => {
    const storedProjectName = localStorage.getItem('current_project_name')
    if (storedProjectName) {
      setProjectName(storedProjectName)
    }

    // Check if connector generation has been completed
    const checkAndLoadConnector = async () => {
      const username = localStorage.getItem('username')
      const projectName = localStorage.getItem('current_project_name')

      if (!username || !projectName) {
        return
      }

      try {
        // Check generation status using the dedicated endpoint
        const statusResponse = await fetch(`${API_BASE}/connector-generation-status/${username}/${projectName}`, {
          credentials: 'include',
        })
        const statusData = await statusResponse.json()

        // Load connector files regardless of generation status
        const filesResponse = await fetch(`${API_BASE}/connector-files/${username}/${projectName}`, {
          credentials: 'include',
        })
        const filesData = await filesResponse.json()

        if (filesData.success) {
          setProjectFiles(filesData.files)

          // Check if connector.py exists (either generated or uploaded)
          const connectorFile = filesData.files.find((file: { name: string }) => file.name === 'connector.py')

          if (connectorFile) {
            // connector.py exists - no generation needed (either generated or uploaded)
            setSelectedFile(connectorFile.name)
            loadFileContent(connectorFile.name)
            loadChatHistory()
            setNeedsGeneration(false)
            setShowRightPanel(true) // Show the files panel for ready-to-use projects
          } else if (statusData.success && statusData.generation_complete) {
            // Generation marked complete but no connector.py (edge case)
            loadChatHistory()
            setNeedsGeneration(false)
          } else {
            // No connector.py and generation not complete - show generate button
            setNeedsGeneration(true)
            loadChatHistory()
          }
        } else {
          // Failed to load files - show generate button
          setNeedsGeneration(true)
          loadChatHistory()
        }
      } catch (error) {
        console.error('Error checking connector status:', error)
        // On error, show generate button
        setNeedsGeneration(true)
      }
    }

    checkAndLoadConnector()
  }, [])

  // Update Monaco Editor when codeContent changes
  useEffect(() => {
    if (monacoEditor && codeContent !== undefined) {
      monacoEditor.setValue(codeContent)
    }
  }, [codeContent, monacoEditor])

  // Auto-scroll logs container to bottom when logs change
  useEffect(() => {
    const logsContainer = document.getElementById('debug-logs-scrollable')
    if (logsContainer) {
      logsContainer.scrollTop = logsContainer.scrollHeight
    }
  }, [logs])

  // Auto-scroll chat container to bottom when new messages arrive
  useEffect(() => {
    const chatContainer = document.getElementById('chat-container')
    if (chatContainer) {
      chatContainer.scrollTop = chatContainer.scrollHeight
    }
  }, [chatMessages])

  const formatLogMessage = (level: string, message: string) => {
    // Remove timestamp prefix if present (like [timestamp])
    const cleanMessage = message.replace(/^\[\d{1,2}:\d{2}:\d{2}\]\s*/, '')

    switch (level) {
      case 'INFO':
        // Only add emoji if not already present to avoid double emojis
        if (cleanMessage.includes('🚀')) {
          return `**${cleanMessage}**`
        } else if (cleanMessage.includes('Starting')) {
          return `🚀 **${cleanMessage}**`
        } else if (cleanMessage.includes('✅')) {
          return cleanMessage
        } else if (cleanMessage.includes('success')) {
          return `✅ ${cleanMessage}`
        } else if (cleanMessage.includes('📦')) {
          return cleanMessage
        } else if (cleanMessage.includes('Generating')) {
          return `📦 ${cleanMessage}`
        } else if (cleanMessage.includes('App dir:') || cleanMessage.includes('Workspace:') || cleanMessage.includes('Command:')) {
          return `🔧 \`${cleanMessage}\``
        } else {
          return cleanMessage
        }
      
      case 'SUCCESS':
        // Don't add emoji if already present
        if (cleanMessage.includes('✅')) {
          return `**${cleanMessage}**`
        }
        return `✅ **${cleanMessage}**`
      
      case 'ERROR':
        return `❌ **Error:** ${cleanMessage}`
      
      case 'WARNING':
        return `⚠️ **Warning:** ${cleanMessage}`
      
      default:
        return `📝 ${cleanMessage}`
    }
  }

  const isDatabaseFile = (filename: string): boolean => {
    return filename?.endsWith('warehouse.db') || filename?.includes('files/warehouse.db') || false
  }

  const formatHistoricalAIMessage = (rawText: string): string => {
    // Process historical AI messages that contain log prefixes to match streaming format
    if (!rawText) return rawText
    
    const lines = rawText.split('\n')
    const formattedLines: string[] = []
    
    for (const line of lines) {
      // Check if line has log prefix format: [LEVEL] message
      const logMatch = line.match(/^\[([A-Z]+)\]\s*(.*)$/)
      
      if (logMatch) {
        const [, level, message] = logMatch
        // Apply the same formatting as streaming messages
        const formattedMessage = formatLogMessage(level, message)
        formattedLines.push(formattedMessage)
      } else if (line.trim()) {
        // Line without log prefix - keep as is (might be user content or formatted content)
        formattedLines.push(line)
      }
      // Skip empty lines to reduce clutter
    }
    
    // Join with double newlines for better spacing, similar to streaming
    return formattedLines.join('\n\n')
  }

  const streamGenerationLogs = async (projectName: string) => {
    const username = localStorage.getItem('username')

    // Reset test logs cleared flag for new generation
    testLogsClearedRef.current = false

    if (!username) {
      console.error('Missing username')
      return
    }

    // Auto-exit edit mode when starting generation stream
    if (isEditing) {
      handleCancelEdit()
    }
    // Create abort controller for this request
    const controller = new AbortController()
    setAbortController(controller)
    setLoading(true)
    const startTime = Date.now()
    let wasManuallyStopped = false

    try {
      // Call the streaming generation endpoint
      const response = await authenticatedFetch(`${API_BASE}/generate-connector-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_name: projectName
          // description is read from JSON file on backend
        }),
        signal: controller.signal
      })

      if (!response.ok) {
        throw new Error('Network response was not ok')
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let aiResponseText = ''

      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          const chunk = decoder.decode(value)
          const lines = chunk.split('\n')
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                
                if (data.type === 'config_review') {
                  // Configuration review required before testing
                  console.log('Config review required:', data.configuration)

                  // Use sensitive_fields from backend if provided, otherwise auto-detect
                  const sensitiveFieldsSet = new Set<string>()
                  if (data.sensitive_fields && Array.isArray(data.sensitive_fields)) {
                    // Use backend's list (from .config_metadata.json)
                    data.sensitive_fields.forEach((field: string) => sensitiveFieldsSet.add(field))
                    console.log('Using sensitive_fields from backend:', data.sensitive_fields)
                  } else {
                    // Fall back to auto-detection from field names
                    Object.keys(data.configuration).forEach(key => {
                      const lowerKey = key.toLowerCase()
                      if (lowerKey.includes('key') || lowerKey.includes('secret') ||
                          lowerKey.includes('password') || lowerKey.includes('token') ||
                          lowerKey.includes('credential')) {
                        sensitiveFieldsSet.add(key)
                      }
                    })
                  }

                  setConfigData(data.configuration)
                  setSensitiveFields(sensitiveFieldsSet)
                  setConfigContext('generation')  // Set context to generation
                  setShowConfigReview(true)

                  // Add message to chat
                  aiResponseText += '⏸️ **Configuration Review Required**\n\nPlease review and confirm the connector configuration before testing...\n\n'
                  setChatMessages(prev => {
                    const newMessages = [...prev]
                    for (let i = newMessages.length - 1; i >= 0; i--) {
                      if (newMessages[i].type === 'ai') {
                        newMessages[i] = {
                          ...newMessages[i],
                          text: aiResponseText
                        }
                        break
                      }
                    }
                    return newMessages
                  })
                } else if (data.type === 'log') {
                  // Format log message for chat display with better styling
                  const formattedMessage = formatLogMessage(data.level, data.message)
                  aiResponseText += formattedMessage + '\n\n'

                  setChatMessages(prev => {
                    const newMessages = [...prev]
                    // Find the last AI message and update it
                    for (let i = newMessages.length - 1; i >= 0; i--) {
                      if (newMessages[i].type === 'ai') {
                        newMessages[i] = {
                          ...newMessages[i],
                          text: aiResponseText
                        }
                        break
                      }
                    }
                    return newMessages
                  })
                } else if (data.type === 'test_log') {
                  // Clear logs on first test_log message (like manual debug)
                  if (!testLogsClearedRef.current) {
                    setLogs([])
                    testLogsClearedRef.current = true
                    setShowRightPanel(true) // Show the side panel
                    setActiveTab('logs') // Switch to logs tab to show test progress
                  }
                  // Route test logs to logs tab only (not chat)
                  addLog(data.level, data.message)
                } else if (data.type === 'completion') {
                  // Final message received - calculate response time
                  const endTime = Date.now()
                  const responseTime = Math.round((endTime - startTime) / 1000)
                  
                  // Handle different completion statuses
                  if (data.status === 'success') {
                    aiResponseText += '\n---\n\n🎉 **Generation Complete!**\n\nYour connector has been successfully generated and is ready to use. You can now:\n\n• View the generated files in the file explorer\n• Test your connector\n• Deploy to Fivetran\n\n✨ Happy connecting!'
                  } else if (data.status === 'success_after_fix') {
                    aiResponseText += '\n---\n\n🎉 **Generation Complete (Auto-Fixed)!**\n\nYour connector encountered some issues during generation, but they were automatically resolved! The connector is now ready to use:\n\n• View the generated files in the file explorer\n• Test your connector\n• Deploy to Fivetran\n\n🔧 Auto-fix worked perfectly! ✨'
                  } else if (data.status === 'user_error') {
                    aiResponseText += '\n---\n\n⚠️ **Configuration Issue Detected**\n\n' + (data.message || 'A configuration issue was detected.') + '\n\n💡 **Action Required:**\n' + (data.guidance || 'Please check your API credentials, network connectivity, permissions, and configuration settings.') + '\n\n🔄 After making the necessary changes, try generating again.'
                  } else if (data.status === 'error_fix_failed') {
                    aiResponseText += '\n---\n\n❌ **Generation Failed (Auto-Fix Attempted)**\n\n' + (data.message || 'Generation failed and auto-fix was attempted but unsuccessful.') + '\n\n🔧 **What happened:** The AI tried to automatically fix the issues but couldn\'t resolve them completely.\n\n📋 **Next steps:** Please check the logs above for specific errors or try again with a modified description.'
                  } else {
                    aiResponseText += '\n---\n\n❌ **Generation Failed**\n\n' + (data.message || 'An error occurred during generation.') + '\n\nPlease check the logs above for more details or try again.'
                  }
                  
                  // Update the AI message with final content and response time
                  setChatMessages(prev => {
                    const newMessages = [...prev]
                    // Find the last AI message and update it
                    for (let i = newMessages.length - 1; i >= 0; i--) {
                      if (newMessages[i].type === 'ai') {
                        newMessages[i] = {
                          ...newMessages[i],
                          text: aiResponseText,
                          responseTime: responseTime
                        }
                        break
                      }
                    }
                    return newMessages
                  })
                  
                  // Reload files after successful generation (including auto-fixed)
                  if (data.status === 'success' || data.status === 'success_after_fix') {
                    loadProjectFiles(true)
                  } else {
                    // Generation failed - show Generate button so user can retry
                    setNeedsGeneration(true)
                  }
                  break
                } else {
                  // Handle unknown data types silently
                }
              } catch (e) {
                // Handle parsing errors silently
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('Error during generation streaming:', error)
      
      // Check if the error is due to abort
      if (error instanceof Error && error.name === 'AbortError') {
        // Request was aborted, don't show error message
        wasManuallyStopped = true
      } else {
        // Update the AI message with error
        setChatMessages(prev => {
          const newMessages = [...prev]
          // Find the last AI message and update it
          for (let i = newMessages.length - 1; i >= 0; i--) {
            if (newMessages[i].type === 'ai') {
              newMessages[i] = {
                ...newMessages[i],
                text: '❌ **Generation Error**\n\nSorry, there was an unexpected error during connector generation.\n\n**What you can try:**\n• Check your internet connection\n• Verify your project details\n• Try again in a few moments\n\nIf the problem persists, please contact support.'
              }
              break
            }
          }
          return newMessages
        })
        // Show Generate button so user can retry
        setNeedsGeneration(true)
      }
    } finally {
      setLoading(false)
      // Reload files to reflect any changes made during generation (success or failure)
      loadProjectFiles(true)
      // Only clear abortController if it wasn't manually stopped
      if (!wasManuallyStopped) {
        setAbortController(null)
      }
    }
  }

  const sendInitialGenerationMessage = async () => {
    try {
      const username = localStorage.getItem('username')

      if (!username) return

      // Get project name and description from localStorage (set by CreateConnectorPage)
      const projectName = localStorage.getItem('current_project_name')
      const projectDescription = localStorage.getItem('current_project_description')

      if (!projectName) return

      // Hide the generate button since we're starting
      setNeedsGeneration(false)

      // Simple message - spec is shown in collapsible section above chat
      const initialMessage = `Generating connector: **${projectName}**`

      // Create user message bubble
      const userMessage: ChatMessage = { type: 'user', text: initialMessage, timestamp: new Date().toISOString() }

      // Create placeholder AI message for streaming
      const aiMessage: ChatMessage = { type: 'ai', text: '', timestamp: new Date().toISOString() }

      // Add both messages at once to prevent race conditions
      setChatMessages(prev => [...prev, userMessage, aiMessage])

      // Save the initial message to chat history
      try {
        await authenticatedFetch(`${API_BASE}/connector-chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            username,
            connector_name: projectName,
            message: initialMessage
          })
        })
      } catch (error) {
        console.error('Failed to save initial message to chat history:', error)
      }

      // Start generation with streaming logs - backend reads description from JSON file
      await streamGenerationLogs(projectName)
    } catch (error) {
      console.error('Error sending initial generation message:', error)
    }
  }

  const loadChatHistory = async () => {
    try {
      const username = localStorage.getItem('username')
      const projectName = localStorage.getItem('current_project_name')

      if (!username || !projectName) return

      // Fetch chat history and project data in parallel
      const [chatResponse, projectResponse] = await Promise.all([
        authenticatedFetch(`${API_BASE}/connector-chat/${username}/${projectName}`),
        authenticatedFetch(`${API_BASE}/project-data/${username}/${projectName}`)
      ])

      const chatData = await chatResponse.json()
      const projectData = await projectResponse.json()

      // Store project description in state for collapsible spec section
      // Don't show description for uploaded projects (they don't have a meaningful spec)
      if (projectData.success && projectData.project?.description && projectData.project?.type !== 'uploaded') {
        setProjectDescription(projectData.project.description)
      } else {
        setProjectDescription('')
      }

      if (chatData.success) {
        // Process historical AI messages to match streaming format
        const processedMessages = chatData.messages.map((message: ChatMessage) => {
          if (message.type === 'ai' && message.text) {
            // Check if this looks like a historical log dump with [LEVEL] prefixes
            const hasLogPrefixes = message.text.includes('[INFO]') ||
                                   message.text.includes('[SUCCESS]') ||
                                   message.text.includes('[ERROR]') ||
                                   message.text.includes('[WARNING]')

            if (hasLogPrefixes) {
              return {
                ...message,
                text: formatHistoricalAIMessage(message.text)
              }
            }
          }
          return message
        })

        setChatMessages(processedMessages)
      }
    } catch (error) {
      console.error('Error loading chat history:', error)
    }
  }

  const loadProjectFiles = async (autoSelectFirst = false) => {
    try {
      // Set loading state for fade effect
      setFilesLoading(true)

      // Refresh session before file operations
      await refreshSession()

      const username = localStorage.getItem('username')
      const projectName = localStorage.getItem('current_project_name')

      if (!username || !projectName) return

      const response = await authenticatedFetch(`${API_BASE}/connector-files/${username}/${projectName}`)

      const data = await response.json()

      if (data.success) {
        setProjectFiles(data.files)
        // Only auto-select file if explicitly requested
        if (autoSelectFirst && data.files.length > 0) {
          // Prefer connector.py if available, otherwise select first file
          const connectorFile = data.files.find(file => file.name === 'connector.py')
          const fileToSelect = connectorFile || data.files[0]
          setSelectedFile(fileToSelect.name)
          loadFileContent(fileToSelect.name)
        }
      }
      
      // Add 0.4 second delay for fade effect (matches page transitions)
      setTimeout(() => {
        setFilesLoading(false)
      }, 400)
    } catch (error) {
      console.error('Error loading project files:', error)
      // Clear loading state even on error
      setTimeout(() => {
        setFilesLoading(false)
      }, 400)
    }
  }

  const loadFileContent = async (filename: string) => {
    try {
      // Refresh session before file operations
      await refreshSession()

      const username = localStorage.getItem('username')
      const projectName = localStorage.getItem('current_project_name')

      if (!username) {
        console.error('No username found in localStorage')
        return
      }

      if (!projectName) {
        console.error('No project name found')
        return
      }

      const response = await authenticatedFetch(`${API_BASE}/connector-file/${username}/${projectName}/${filename}`)

      const data = await response.json()

      if (data.success) {
        // Check if this is a config file that failed to decrypt
        if (data.decrypt_failed) {
          setConfigDecryptFailed(true)
          setConfigDecryptMessage(data.message || 'Configuration was encrypted by a different user or system.')
          setCodeContent('')
        } else {
          setConfigDecryptFailed(false)
          setConfigDecryptMessage('')
          setCodeContent(data.content)
        }
      } else {
        console.error('File load failed:', data)
      }
    } catch (error) {
      console.error('Error loading file content:', error)
    }
  }



  const addLog = (level: string, message: string) => {
    const timestamp = new Date().toLocaleString()
    setLogs(prev => [...prev, { timestamp, level, message }])
  }

  const parseLogLevel = (message: string): { level: string, message: string } => {
    // Try to extract log level from various formats:
    // Format 1: [timestamp] LEVEL: message
    // Format 2: timestamp LEVEL: message (Fivetran CLI format)
    // Format 3: ERROR: message (stderr prefix)

    // Check for SEVERE (Fivetran CLI uses this for errors)
    if (message.includes(' SEVERE:') || message.includes('] SEVERE:')) {
      const cleanedMessage = message.replace(/.*SEVERE:\s*/, '')
      return { level: 'ERROR', message: cleanedMessage }
    }

    // Check for ERROR
    if (message.includes(' ERROR:') || message.includes('] ERROR:') || message.startsWith('ERROR:')) {
      const cleanedMessage = message.replace(/.*ERROR:\s*/, '')
      return { level: 'ERROR', message: cleanedMessage }
    }

    // Check for WARNING
    if (message.includes(' WARNING:') || message.includes('] WARNING:') || message.includes(' WARN:')) {
      const cleanedMessage = message.replace(/.*WARN(?:ING)?:\s*/, '')
      return { level: 'WARNING', message: cleanedMessage }
    }

    // Check for INFO
    if (message.includes(' INFO:') || message.includes('] INFO:')) {
      const cleanedMessage = message.replace(/.*INFO:\s*/, '')
      return { level: 'INFO', message: cleanedMessage }
    }

    // Default to INFO if no level found
    return { level: 'INFO', message }
  }

  const addDeployLog = (level: string, message: string) => {
    const timestamp = new Date().toLocaleString()
    setDeployLogs(prev => [...prev, { timestamp, level, message }])
  }

  // Auto-scroll deploy logs to bottom when new logs arrive
  useEffect(() => {
    if (deployLogsRef.current) {
      deployLogsRef.current.scrollTop = deployLogsRef.current.scrollHeight
    }
  }, [deployLogs])

  const handleDeploy = () => {
    // Pre-fill connector name with current project value
    const currentProjectName = localStorage.getItem('current_project_name') || ''
    setDeployForm(prev => ({
      ...prev,
      connectorName: currentProjectName
    }))
    // Clear deploy logs and errors when opening dialog
    setDeployLogs([])
    setDeployError('')
    setDeployStatus(null)
    setShowDeployDialog(true)
  }

  const handleDeploySubmit = async () => {
    // Clear any previous errors and status
    setDeployError('')
    setDeployStatus('running')
    
    // Validate required fields
    if (!deployForm.connectorName.trim()) {
      setDeployError('Connector name is required')
      return
    }

    // Validate connector name format
    const nameError = validateProjectName(deployForm.connectorName, [])
    if (nameError) {
      setDeployError(nameError)
      return
    }

    if (!deployForm.destinationName.trim()) {
      setDeployError('Destination name is required')
      return
    }

    if (!deployForm.apiKey.trim()) {
      setDeployError('API key is required')
      return
    }
    
    // Auto-exit edit mode when starting deploy
    if (isEditing) {
      handleCancelEdit()
    }
    setDeployLoading(true)
    
    try {
      const currentProjectName = localStorage.getItem('current_project_name')

      if (!currentProjectName) {
        setDeployError('No project selected - please select a project first')
        return
      }

      // Clear existing deploy logs first
      setDeployLogs([])

      // Call the streaming deploy endpoint
      const response = await authenticatedFetch(`${API_BASE}/deploy-connector`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_name: currentProjectName,
          connector_name: deployForm.connectorName,
          destination_name: deployForm.destinationName,
          api_key: deployForm.apiKey,
          include_config: deployForm.includeConfig,
          force_deployment: deployForm.forceDeployment
        }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        setDeployError(errorData.detail || 'Deploy request failed')
        return
      }

      // Handle streaming response
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          const chunk = decoder.decode(value)
          const lines = chunk.split('\n')
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const rawMessage = line.slice(6).trim()
              if (rawMessage === '[DONE]') {
                break
              }
              if (rawMessage) {
                // Parse log level from message
                const { level, message } = parseLogLevel(rawMessage)
                addDeployLog(level, message)

                // Detect deployment success or failure from log messages
                if (rawMessage.includes('✅ Deployment completed successfully')) {
                  setDeployStatus('success')
                } else if (rawMessage.includes('❌ Deployment failed with exit code:') ||
                           rawMessage.includes('Deployment failed')) {
                  setDeployStatus('failed')
                }
              }
            }
          }
        }
      }
      
    } catch (error) {
      console.error('Error during deployment:', error)
      addDeployLog('ERROR', `Deployment error: ${error}`)
      setDeployError(`Deployment failed: ${error}`)
      setDeployStatus('failed')
    } finally {
      setDeployLoading(false)
      // Reload files to reflect any changes made during deployment (success or failure)
      loadProjectFiles(true)
    }
  }

  const handleDeployCancel = () => {
    setShowDeployDialog(false)
    setDeployLogs([])
    setDeployError('')
    setDeployStatus(null)
    setDeployForm({
      connectorName: '',
      destinationName: '',
      includeConfig: true,
      forceDeployment: true,
      apiKey: ''
    })
    setShowApiKey(false)
  }

  const handleDebug = async () => {
    // Auto-exit edit mode when starting debug
    if (isEditing) {
      handleCancelEdit()
    }

    const username = localStorage.getItem('username')
    const projectName = localStorage.getItem('current_project_name')

    if (!username || !projectName) {
      console.error('Missing username or project name')
      addLog('ERROR', 'Missing required information')
      return
    }

    // Step 1: Check if configuration exists and fetch it
    try {
      const configResponse = await authenticatedFetch(`${API_BASE}/get-config/${projectName}`)

      if (configResponse.ok) {
        const configResult = await configResponse.json()

        if (configResult.exists && Object.keys(configResult.configuration).length > 0) {
          // Configuration exists - check if already encrypted (credentials entered)
          console.log('Config exists, encrypted:', configResult.encrypted)

          // If config is encrypted, credentials have been entered - skip dialog and run
          if (configResult.encrypted) {
            console.log('Config is encrypted, proceeding to run')
            await runDebugStream()
            return
          }

          // Config is not encrypted - show dialog to enter credentials
          // Auto-detect sensitive fields based on field name patterns
          const initialSensitiveFields = new Set<string>()
          Object.keys(configResult.configuration).forEach(key => {
            const lowerKey = key.toLowerCase()
            if (lowerKey.includes('key') || lowerKey.includes('secret') ||
                lowerKey.includes('password') || lowerKey.includes('token') ||
                lowerKey.includes('credential')) {
              initialSensitiveFields.add(key)
            }
          })
          console.log('Auto-detected sensitive fields:', Array.from(initialSensitiveFields))

          setConfigData(configResult.configuration)
          setSensitiveFields(initialSensitiveFields)
          setConfigContext('debug')  // Set context to debug
          setShowConfigReview(true)

          // Don't proceed with debug yet - wait for user to submit config
          return
        }
      }
    } catch (error) {
      console.error('Error checking configuration:', error)
      // Continue with debug even if config check fails
    }

    // Step 2: No config or config check failed - proceed directly with debug
    await runDebugStream()
  }

  const runDebugStream = async () => {
    setDebugLoading(true)

    // Create debug abort controller for this request
    const controller = new AbortController()
    setDebugAbortController(controller)

    try {
      const username = localStorage.getItem('username')
      const projectName = localStorage.getItem('current_project_name')

      if (!username || !projectName) {
        console.error('Missing username or project name')
        addLog('ERROR', 'Missing required information')
        return
      }

      // Clear existing logs first
      setLogs([])
      setPendingAIFixLogs(null) // Clear any pending AI fix
      testLogsClearedRef.current = false // Reset flag for consistent behavior

      // Show the right panel and switch to Logs tab
      setShowRightPanel(true)
      setActiveTab('logs')

      // Add initial debug log
      addLog('INFO', 'Starting debug session...')

      // Call the debug endpoint with abort signal
      const response = await authenticatedFetch(`${API_BASE}/debug-connector-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_name: projectName,
          trigger_context: "manual"
        }),
        signal: controller.signal
      })

      if (!response.ok) {
        throw new Error(`Debug request failed: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No response body')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))

              if (data.type === 'log') {
                addLog(data.level, data.message)
              } else if (data.type === 'test_log') {
                // Clear logs on first test_log message (like manual debug)
                if (!testLogsClearedRef.current) {
                  setLogs([])
                  testLogsClearedRef.current = true
                  setShowRightPanel(true) // Show the side panel
                  setActiveTab('logs') // Switch to logs tab to show test progress
                }
                // Route test logs to logs tab
                addLog(data.level, data.message)
              } else if (data.type === 'complete') {
                if (data.success) {
                  if (data.fixed) {
                    addLog('SUCCESS', '✅ Debug run completed successfully after auto-fix!')
                    addLog('INFO', 'The connector was automatically fixed and is ready to test again.')
                  } else {
                    addLog('SUCCESS', 'Debug session completed successfully')
                  }
                  // Reload files and chat history after successful debug (including auto-fixed)
                  loadProjectFiles(true)
                  loadChatHistory()
                } else {
                  // Handle different error types
                  if (data.error_type === 'user_config') {
                    addLog('WARNING', '⚠️ Configuration Error: Please check your credentials and network settings')
                    addLog('INFO', data.message || 'Debug failed due to configuration issues')
                    setPendingAIFixLogs(null) // Clear any pending AI fix
                  } else if (data.offer_ai_fix && data.log_content) {
                    // Debug failed but AI fix is available
                    addLog('ERROR', data.message || 'Debug failed')
                    addLog('INFO', '💡 AI can attempt to fix this issue automatically.')
                    setPendingAIFixLogs(JSON.stringify(data.log_content)) // Store logs for AI fix
                  } else {
                    addLog('ERROR', data.message || `Debug failed with return code: ${data.return_code}`)
                    setPendingAIFixLogs(null) // Clear any pending AI fix
                  }
                  // Reload chat history to show the debug failure message in chat window
                  loadChatHistory()
                }
              } else if (data.type === 'error') {
                addLog('ERROR', data.message)
              }
            } catch (e) {
              console.error('Error parsing debug response:', e)
            }
          }
        }
      }
      
    } catch (error) {
      console.error('Error during debug:', error)
      addLog('ERROR', `Debug error: ${error}`)
    } finally {
      setDebugLoading(false)
      setDebugAbortController(null)
      // Reload files to reflect any changes made during debug (success or failure)
      loadProjectFiles(true)
    }
  }

  // Trigger AI fix when user clicks "Let AI fix" button
  const triggerAIFix = async () => {
    const projectName = localStorage.getItem('current_project_name')

    if (!projectName || !pendingAIFixLogs) {
      console.error('Missing project name or log content')
      return
    }

    setAiFixLoading(true)
    setPendingAIFixLogs(null) // Clear the pending logs
    setShowRightPanel(true)
    setActiveTab('logs')
    addLog('INFO', '🔧 Starting AI fix...')

    // Add initial AI message to chat that we'll update
    const aiMessageTimestamp = new Date().toISOString()
    setChatMessages(prev => [...prev, {
      type: 'ai',
      text: '🔧 **AI Fix in Progress**\n\nAnalyzing the error and attempting to fix...',
      timestamp: aiMessageTimestamp
    }])

    let streamedContent: string[] = []

    try {
      const response = await authenticatedFetch(`${API_BASE}/trigger-ai-fix-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_name: projectName,
          log_content: pendingAIFixLogs
        })
      })

      if (!response.ok) {
        throw new Error(`AI fix request failed: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No response body')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))

              if (data.type === 'log') {
                addLog(data.level, data.message)

                // Stream relevant progress to chat (filter verbose messages)
                const message = data.message || ''
                if (message.includes('ERROR_TYPE:') ||
                    message.includes('PROBLEM IDENTIFIED:') ||
                    message.includes('SOLUTION APPLIED:') ||
                    message.includes('FILES MODIFIED:') ||
                    message.includes('🔧 CODE ISSUE') ||
                    message.includes('🔍 USER CONFIGURATION')) {
                  streamedContent.push(message)
                  // Update the streaming chat message
                  setChatMessages(prev => {
                    const updated = [...prev]
                    const lastIdx = updated.length - 1
                    if (lastIdx >= 0 && updated[lastIdx].timestamp === aiMessageTimestamp) {
                      updated[lastIdx] = {
                        ...updated[lastIdx],
                        text: '🔧 **AI Fix in Progress**\n\n' + streamedContent.join('\n')
                      }
                    }
                    return updated
                  })
                }
              } else if (data.type === 'complete') {
                if (data.success) {
                  addLog('SUCCESS', '✅ AI fix completed! Please run debug again to verify.')
                  // Reload files and chat history after successful fix
                  loadProjectFiles(true)
                  loadChatHistory()
                } else {
                  addLog('ERROR', data.message || 'AI fix failed')
                  // Reload chat history to show AI fix failure message
                  loadChatHistory()
                }
              } else if (data.type === 'config_review') {
                // Handle config review popup if needed during AI fix
                setConfigReview({
                  show: true,
                  configuration: data.configuration,
                  sensitiveFields: data.sensitive_fields || []
                })
              } else if (data.type === 'error') {
                addLog('ERROR', data.message)
              }
            } catch (e) {
              console.error('Error parsing AI fix response:', e)
            }
          }
        }
      }

    } catch (error) {
      console.error('Error during AI fix:', error)
      addLog('ERROR', `AI fix error: ${error}`)
      // Update chat message with error
      setChatMessages(prev => {
        const updated = [...prev]
        const lastIdx = updated.length - 1
        if (lastIdx >= 0 && updated[lastIdx].timestamp === aiMessageTimestamp) {
          updated[lastIdx] = {
            ...updated[lastIdx],
            text: '🔧 **AI Fix Failed**\n\n' + (streamedContent.length > 0 ? streamedContent.join('\n') + '\n\n' : '') + `Error: ${error}`
          }
        }
        return updated
      })
    } finally {
      setAiFixLoading(false)
      loadProjectFiles(true)
    }
  }

  const stopGeneration = async () => {
    if (abortController && !stopping) {
      // Show immediate feedback
      setStopping(true)

      // Kill backend process first
      const projectName = localStorage.getItem('current_project_name')
      if (projectName) {
        try {
          const controller = new AbortController()
          const timeoutId = setTimeout(() => controller.abort(), 3000) // 3 second timeout

          await authenticatedFetch(`${API_BASE}/kill-generation`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ project_name: projectName }),
            signal: controller.signal
          })
          clearTimeout(timeoutId)
        } catch (error) {
          console.warn('Kill-generation request failed:', error)
        }
      }

      // Abort the frontend request
      abortController.abort()
      setAbortController(null)
      setLoading(false)
      setStopping(false)

      // Update the AI message to show it was stopped
      setChatMessages(prev => {
        const newMessages = [...prev]
        if (newMessages.length > 0 && newMessages[newMessages.length - 1].type === 'ai') {
          const existingText = newMessages[newMessages.length - 1].text?.trim() || ''
          const interruptedMessage = '⏹️ **Interrupted**\n\n_Generation was stopped by user._'

          // Check if existing text is meaningful (not just numbers, whitespace, or very short)
          // Meaningful text: longer than 20 chars AND contains letters
          const hasMeaningfulContent = existingText.length > 20 && /[a-zA-Z]{3,}/.test(existingText)

          newMessages[newMessages.length - 1] = {
            ...newMessages[newMessages.length - 1],
            text: hasMeaningfulContent
              ? existingText + '\n\n' + interruptedMessage
              : interruptedMessage
          }
        }
        return newMessages
      })

      // Show generate button again so user can restart
      setNeedsGeneration(true)
    }
  }

  const stopDebug = async () => {
    if (debugAbortController) {
      // Kill the backend debug process first
      const projectName = localStorage.getItem('current_project_name')
      if (projectName) {
        try {
          const controller = new AbortController()
          const timeoutId = setTimeout(() => controller.abort(), 3000) // 3 second timeout

          await authenticatedFetch(`${API_BASE}/kill-debug`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ project_name: projectName }),
            signal: controller.signal
          })
          clearTimeout(timeoutId)
        } catch (error) {
          console.warn('Kill debug request failed:', error)
        }
      }

      // Abort the frontend request
      debugAbortController.abort()
      setDebugAbortController(null)
      setDebugLoading(false)

      // Add log message showing debug was stopped
      addLog('WARNING', 'Debug process stopped by user')
    }
  }

  // Centralized helper to stop all running AI operations
  const stopAllOperations = () => {
    if (loading && abortController) {
      abortController.abort()
      setAbortController(null)
      setLoading(false)
    }
    if (debugLoading && debugAbortController) {
      debugAbortController.abort()
      setDebugAbortController(null)
      setDebugLoading(false)
    }
  }

  // Check if any AI operation is currently running
  const isAnyOperationRunning = () => loading || debugLoading

  const handleNavigateHome = async () => {
    if (isAnyOperationRunning()) {
      const confirmed = window.confirm(
        'An AI operation is in progress. Are you sure you want to leave? The operation will be stopped.'
      )
      if (!confirmed) {
        return
      }
      stopAllOperations()
    }
    navigate('/')
  }

  const handleDeleteConnector = async () => {
    const connectorName = localStorage.getItem('current_project_name')
    if (!connectorName) {
      alert('No connector selected')
      return
    }

    const confirmed = window.confirm(
      `Are you sure you want to delete "${connectorName}"? This action cannot be undone.`
    )
    if (!confirmed) {
      return
    }

    // Stop any running operations first
    stopAllOperations()

    try {
      const response = await authenticatedFetch(`${API_BASE}/delete-connector`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ connector_name: connectorName })
      })

      const result = await response.json()

      if (result.success) {
        // Clear localStorage and navigate home
        localStorage.removeItem('current_project_name')
        localStorage.removeItem('current_project_description')
        navigate('/')
      } else {
        alert(`Failed to delete connector: ${result.detail || result.message || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Error deleting connector:', error)
      alert('Failed to delete connector. Please try again.')
    }
  }

  const sendMessage = async () => {
    if (!chatInput.trim() || loading) return

    // Refresh session before chat operations
    await refreshSession()

    // Reset test logs cleared flag for new smart interaction
    testLogsClearedRef.current = false

    const username = localStorage.getItem('username')
    const projectName = localStorage.getItem('current_project_name')
    
    if (!username) {
      alert('Please login first')
      return
    }

    if (!projectName) {
      alert('Please create or select a connector first')
      return
    }

    // Auto-exit edit mode when starting chat interaction
    if (isEditing) {
      handleCancelEdit()
    }
    // Create abort controller for this request
    const controller = new AbortController()
    setAbortController(controller)
    setLoading(true)
    const startTime = Date.now()
    
    const userMessage: ChatMessage = { type: 'user', text: chatInput, timestamp: new Date().toISOString() }
    setChatMessages(prev => [...prev, userMessage])
    setChatInput('')

    // Add a placeholder AI message for streaming
    const aiMessage: ChatMessage = { type: 'ai', text: '', timestamp: new Date().toISOString() }
    setChatMessages(prev => [...prev, aiMessage])

    try {
      // Use smart endpoint for intelligent routing
      const endpoint = `${API_BASE}/smart-connector-interaction`
      const requestBody = { project_name: projectName, user_message: userMessage.text }

      const response = await authenticatedFetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal
      })

      if (!response.ok) {
        throw new Error('Network response was not ok')
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let aiResponseText = ''

      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          const chunk = decoder.decode(value)
          const lines = chunk.split('\n')
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))

                if (data.type === 'config_review') {
                  // Configuration review required during interactive testing
                  console.log('Config review required (interact):', data.configuration)

                  // Use sensitive_fields from backend if provided, otherwise auto-detect
                  const sensitiveFieldsSet = new Set<string>()
                  if (data.sensitive_fields && Array.isArray(data.sensitive_fields)) {
                    // Use backend's list (from .config_metadata.json)
                    data.sensitive_fields.forEach((field: string) => sensitiveFieldsSet.add(field))
                    console.log('Using sensitive_fields from backend:', data.sensitive_fields)
                  } else {
                    // Fall back to auto-detection from field names
                    Object.keys(data.configuration).forEach(key => {
                      const lowerKey = key.toLowerCase()
                      if (lowerKey.includes('key') || lowerKey.includes('secret') ||
                          lowerKey.includes('token') || lowerKey.includes('password') ||
                          lowerKey.includes('credential')) {
                        sensitiveFieldsSet.add(key)
                      }
                    })
                    console.log('Auto-detected sensitive fields:', Array.from(sensitiveFieldsSet))
                  }
                  setSensitiveFields(sensitiveFieldsSet)

                  setConfigData(data.configuration)
                  setConfigContext('generation')  // Use 'generation' context for interact too
                  setShowConfigReview(true)

                  aiResponseText += '⏸️ **Configuration Review Required**\n\nPlease review and confirm the connector configuration before testing...\n\n'
                  setChatMessages(prev => {
                    const newMessages = [...prev]
                    newMessages[newMessages.length - 1] = {
                      ...newMessages[newMessages.length - 1],
                      text: aiResponseText
                    }
                    return newMessages
                  })
                } else if (data.type === 'log') {
                  // Handle smart interaction logs - maintain streaming format like generation
                  const formattedMessage = formatLogMessage(data.level || 'INFO', data.message)
                  aiResponseText += formattedMessage + '\n\n'

                  setChatMessages(prev => {
                    const newMessages = [...prev]
                    newMessages[newMessages.length - 1] = {
                      ...newMessages[newMessages.length - 1],
                      text: aiResponseText
                    }
                    return newMessages
                  })
                } else if (data.type === 'test_log') {
                  // Clear logs on first test_log message (like manual debug)
                  if (!testLogsClearedRef.current) {
                    setLogs([])
                    testLogsClearedRef.current = true
                    setShowRightPanel(true) // Show the side panel
                    setActiveTab('logs') // Switch to logs tab to show test progress
                  }
                  // Route test logs to logs tab only (not chat)
                  addLog(data.level || 'INFO', data.message)
                } else if (data.type === 'complete') {
                  // Final message received - calculate response time
                  const endTime = Date.now()
                  const responseTime = Math.round((endTime - startTime) / 1000)
                  
                  if (data.success) {
                    aiResponseText += '\n---\n\n✅ **Complete!**\n\nYour request has been processed successfully. You can now:\n\n• View any modified files in the file explorer\n• Test your connector if changes were made\n• Ask follow-up questions\n• Deploy to Fivetran\n\n✨ Happy connecting!'
                  } else {
                    aiResponseText += '\n---\n\n❌ **Request Failed**\n\n' + (data.message || 'An error occurred during processing.') + '\n\nPlease check the logs above for more details or try again.'
                  }
                  
                  // Update the AI message with final content and response time
                  setChatMessages(prev => {
                    const newMessages = [...prev]
                    newMessages[newMessages.length - 1] = {
                      ...newMessages[newMessages.length - 1],
                      text: aiResponseText,
                      responseTime: responseTime
                    }
                    return newMessages
                  })
                  
                  // Reload files after successful revision
                  if (data.success) {
                    loadProjectFiles(true)
                  }
                  break
                }
              } catch (e) {
                // Ignore parsing errors for incomplete chunks
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('Error sending message:', error)
      
      // Check if the error is due to abort
      if (error instanceof Error && error.name === 'AbortError') {
        // Request was aborted, don't show error message
      } else {
        // Update the AI message with error
        setChatMessages(prev => {
          const newMessages = [...prev]
          newMessages[newMessages.length - 1] = {
            ...newMessages[newMessages.length - 1],
            text: 'Sorry, there was an error processing your request. Please try again.'
          }
          return newMessages
        })
      }
    } finally {
      setLoading(false)
      setAbortController(null)
      // Reload files to reflect any changes made during smart interaction (success or failure)
      loadProjectFiles(true)
    }
  }

  const handleFileClick = async (filename: string) => {
    setSelectedFile(filename)
    setConfigDecryptFailed(false)
    setConfigDecryptMessage('')

    // Only load content for non-database files
    if (!isDatabaseFile(filename)) {
      await loadFileContent(filename)
    }

    setIsEditing(false)
  }

  const handleDownloadProject = async () => {
    try {
      const username = localStorage.getItem('username')
      const currentProjectName = localStorage.getItem('current_project_name')

      if (!username || !currentProjectName) {
        alert('Missing authentication or project information')
        return
      }

      const response = await authenticatedFetch(`${API_BASE}/download-project/${username}/${currentProjectName}`)
      
      
      if (response.ok) {
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${currentProjectName}.zip`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
      } else {
        const errorText = await response.text()
        console.error('Failed to download project:', response.status, errorText)
        alert(`Failed to download project files: ${response.status} ${response.statusText}`)
      }
    } catch (error) {
      console.error('Error downloading project:', error)
      alert('Error downloading project files')
    }
  }

  const handleEditCode = () => {
    // For configuration.json, always open the config editor dialog
    // Values are encrypted when saved and decrypted/masked for display
    if (selectedFile === 'configuration.json') {
      handleOpenConfigFromFileViewer()
      return
    }
    setIsEditing(true)
  }


  const handleSaveCode = async () => {
    try {
      const username = localStorage.getItem('username')
      const projectName = localStorage.getItem('current_project_name')
      
      if (!username || !projectName || !monacoEditor) return

      // Get the current content from Monaco Editor
      const currentContent = monacoEditor.getValue()

      // Save the edited content back to the file
      const response = await authenticatedFetch(`${API_BASE}/save-file`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username,
          project_name: projectName,
          filename: selectedFile,
          content: currentContent
        }),
      })

      if (response.ok) {
        setCodeContent(currentContent)
        setIsEditing(false)
        // Reload files to update the modified timestamp without changing selection
        loadProjectFiles(false)
      }
    } catch (error) {
      console.error('Error saving file:', error)
    }
  }

  const handleCancelEdit = () => {
    setIsEditing(false)
    // Reset Monaco Editor content to original
    if (monacoEditor) {
      monacoEditor.setValue(codeContent)
    }
  }

  const handleSubmitConfig = async () => {
    setConfigSubmitting(true)
    try {
      const projectName = localStorage.getItem('current_project_name')

      if (!projectName) {
        console.error('Missing project name')
        return
      }

      const response = await authenticatedFetch(`${API_BASE}/submit-config`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_name: projectName,
          configuration: configData,
          sensitive_fields: Array.from(sensitiveFields)
        })
      })

      if (response.ok) {
        const result = await response.json()
        console.log('Configuration submitted successfully:', result)

        // Close modal
        setShowConfigReview(false)
        setVisibleSensitiveFields(new Set())

        // Check context to determine next action
        if (configContext === 'debug') {
          // Continue with debug after config submission
          console.log('Continuing with debug after config submission')
          await runDebugStream()
        } else if (configContext === 'generation') {
          // Add confirmation message to chat for generation
          setChatMessages(prev => {
            const newMessages = [...prev]
            for (let i = newMessages.length - 1; i >= 0; i--) {
              if (newMessages[i].type === 'ai') {
                newMessages[i] = {
                  ...newMessages[i],
                  text: newMessages[i].text + '\n✅ Configuration confirmed. Proceeding with testing...\n\n'
                }
                break
              }
            }
            return newMessages
          })
        } else if (configContext === 'edit') {
          // Refresh the file content after editing config from file viewer
          // The config is now encrypted, so just reload the file to show the encrypted marker
          await loadFileContent('configuration.json')
        }

        // Reset context
        setConfigContext(null)
      } else {
        // Extract actual error detail from response body
        const errorData = await response.json().catch(() => ({ detail: response.statusText }))
        const errorMsg = errorData.detail || response.statusText
        console.error('Failed to submit configuration:', errorMsg)
        alert(`Failed to submit configuration: ${errorMsg}`)
      }
    } catch (error) {
      console.error('Error submitting configuration:', error)
      alert(`Error submitting configuration: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setConfigSubmitting(false)
    }
  }

  // Open configuration dialog from file viewer when config is encrypted
  const handleOpenConfigFromFileViewer = async () => {
    try {
      const projectName = localStorage.getItem('current_project_name')

      if (!projectName) {
        console.error('Missing project name')
        return
      }

      const configResponse = await authenticatedFetch(`${API_BASE}/get-config/${projectName}`)

      if (configResponse.ok) {
        const configResult = await configResponse.json()

        // Handle case where decryption failed (encrypted by different user/system)
        if (configResult.decrypt_failed) {
          alert(configResult.message || 'Configuration was encrypted by a different user or system. Cannot edit.')
          return
        }

        if (configResult.exists && Object.keys(configResult.configuration).length > 0) {
          // Use saved sensitive fields from backend, or auto-detect based on field name patterns
          const initialSensitiveFields = new Set<string>()
          if (configResult.sensitive_fields && configResult.sensitive_fields.length > 0) {
            // Use saved sensitive fields
            configResult.sensitive_fields.forEach((field: string) => initialSensitiveFields.add(field))
          } else {
            // Auto-detect sensitive fields based on field name patterns
            Object.keys(configResult.configuration).forEach(key => {
              const lowerKey = key.toLowerCase()
              if (lowerKey.includes('key') || lowerKey.includes('secret') ||
                  lowerKey.includes('password') || lowerKey.includes('token') ||
                  lowerKey.includes('credential')) {
                initialSensitiveFields.add(key)
              }
            })
          }

          setConfigData(configResult.configuration)
          setSensitiveFields(initialSensitiveFields)
          setConfigContext('edit')  // Set context to edit
          setShowConfigReview(true)
        } else if (configResult.exists) {
          // Config exists but is empty - still open editor
          setConfigData({})
          setSensitiveFields(new Set())
          setConfigContext('edit')
          setShowConfigReview(true)
        }
      } else {
        console.error('Failed to fetch configuration')
      }
    } catch (error) {
      console.error('Error fetching configuration:', error)
    }
  }

  const handleEditorDidMount = (editor: any) => {
    setMonacoEditor(editor)
  }

  const handleDeleteFile = (filename: string) => {
    setFileToDelete(filename)
    setShowDeleteDialog(true)
  }

  const confirmDeleteFile = async () => {
    if (!fileToDelete) return

    setDeleteLoading(true)
    try {
      const currentProjectName = localStorage.getItem('current_project_name')

      if (!currentProjectName) {
        alert('No project selected')
        return
      }

      const response = await authenticatedFetch(`${API_BASE}/delete-file`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          filename: fileToDelete,
          project_name: currentProjectName
        })
      })

      if (response.ok) {
        const data = await response.json()
        alert(data.message || 'File deleted successfully')
        
        // If the deleted file was currently selected, clear the selection
        if (selectedFile === fileToDelete) {
          setSelectedFile('')
          setCodeContent('')
        }
        
        // Refresh the file list
        loadProjectFiles(false)
      } else {
        const errorData = await response.json()
        alert(errorData.detail || 'Failed to delete file')
      }
    } catch (error) {
      console.error('Error deleting file:', error)
      alert('Error deleting file')
    } finally {
      setDeleteLoading(false)
      setShowDeleteDialog(false)
      setFileToDelete('')
    }
  }

  const cancelDeleteFile = () => {
    setShowDeleteDialog(false)
    setFileToDelete('')
  }

  const handleResetProject = () => {
    setShowResetDialog(true)
  }

  const confirmResetProject = async () => {
    setResetLoading(true)
    try {
      const username = localStorage.getItem('username')
      const currentProjectName = localStorage.getItem('current_project_name')

      if (!username || !currentProjectName) {
        alert('Missing authentication or project information')
        return
      }

      const response = await authenticatedFetch(`${API_BASE}/reset-project/${username}/${currentProjectName}?delete_venv=${resetDeleteVenv}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      })

      if (response.ok) {
        // Close modal and reset checkbox
        setShowResetDialog(false)
        setResetDeleteVenv(false)

        // Refresh the file list without full page reload
        loadProjectFiles()
        setCodeContent('')
        setSelectedFile('')

        // Show success message in chat
        setChatMessages(prev => [...prev, {
          type: 'ai',
          text: '✅ Project reset successfully. All synced data has been cleared.',
          timestamp: new Date().toISOString(),
          responseTime: 0
        }])
      } else {
        const errorText = await response.text()
        alert(`Failed to reset project: ${response.statusText || errorText}`)
      }
    } catch (error) {
      console.error('Error during project reset:', error)
      alert('Error during project reset. Check console for details.')
    } finally {
      setResetLoading(false)
    }
  }

  const cancelResetProject = () => {
    setShowResetDialog(false)
    setResetDeleteVenv(false)
  }

  const getLanguageFromFilename = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase()
    switch (ext) {
      case 'py': return 'python'
      case 'js': return 'javascript'
      case 'ts': return 'typescript'
      case 'json': return 'json'
      case 'html': return 'html'
      case 'css': return 'css'
      case 'md': return 'markdown'
      case 'txt': return 'plaintext'
      default: return 'plaintext'
    }
  }

  const isMarkdownFile = (filename: string) => {
    return filename.toLowerCase().endsWith('.md')
  }

  const filteredFiles = projectFiles.filter(file =>
    file.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // Auto-select first file when search filters out the currently selected file
  useEffect(() => {
    if (filteredFiles.length > 0 && selectedFile) {
      const selectedInFiltered = filteredFiles.some(file => file.name === selectedFile)
      if (!selectedInFiltered) {
        // Current selection not in filtered list - select first available
        handleFileClick(filteredFiles[0].name)
      }
    }
  }, [searchQuery, filteredFiles.length])

  // Organize files by directory structure
  const organizeFilesByDirectory = (files: Array<{name: string, size: number, modified: string}>) => {
    const directories: {[key: string]: Array<{name: string, size: number, modified: string, isSubdirectory?: boolean, subdirectory?: string}>} = {}
    
    // Use the project name as the root directory name
    const rootDirName = projectName || 'Project'
    
    files.forEach(file => {
      const pathParts = file.name.split('/')
      if (pathParts.length === 1) {
        // File in root directory - show under project name
        if (!directories[rootDirName]) directories[rootDirName] = []
        directories[rootDirName].push(file)
      } else {
        // File in subdirectory - show under project name with subdirectory structure
        if (!directories[rootDirName]) directories[rootDirName] = []
        directories[rootDirName].push({
          ...file,
          name: file.name, // Keep full path for display
          isSubdirectory: true,
          subdirectory: pathParts[0]
        })
      }
    })
    
    return directories
  }

  const organizedFiles = organizeFilesByDirectory(filteredFiles)

  // Toggle directory expansion
  const toggleDirectory = (dirName: string) => {
    setExpandedDirectories(prev => ({
      ...prev,
      [dirName]: !prev[dirName]
    }))
  }

  // Resize handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    setIsResizing(true)
    e.preventDefault()
  }

  const handleMouseMove = (e: MouseEvent) => {
    if (!isResizing) return
    
    const containerWidth = window.innerWidth
    const newLeftWidth = (e.clientX / containerWidth) * 100
    
    // Constrain between 20% and 60%
    const constrainedWidth = Math.min(Math.max(newLeftWidth, 20), 60)
    setLeftPanelWidth(constrainedWidth)
  }

  const handleMouseUp = () => {
    setIsResizing(false)
    setIsResizingFileExplorer(false)
  }

  const handleFileExplorerMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizingFileExplorer(true)
  }

  const handleFileExplorerMouseMove = (e: MouseEvent) => {
    if (!isResizingFileExplorer) return
    
    const rightPanel = document.querySelector('[data-right-panel]') as HTMLElement
    if (!rightPanel) return
    
    const rect = rightPanel.getBoundingClientRect()
    const newFileExplorerWidth = e.clientX - rect.left
    
    // Constrain between 200px and 400px
    const constrainedWidth = Math.min(Math.max(newFileExplorerWidth, 200), 400)
    setFileExplorerWidth(constrainedWidth)
  }

  // Add global mouse event listeners
  useEffect(() => {
    if (isResizing || isResizingFileExplorer) {
      if (isResizing) {
        document.addEventListener('mousemove', handleMouseMove)
      }
      if (isResizingFileExplorer) {
        document.addEventListener('mousemove', handleFileExplorerMouseMove)
      }
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    } else {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mousemove', handleFileExplorerMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mousemove', handleFileExplorerMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing, isResizingFileExplorer])


  return (
    <div className="page-fade-in" style={{ 
      height: '100vh', 
      background: '#1B1818',
      color: '#FDFCFB', 
      display: 'flex', 
      flexDirection: 'column',
      overflow: 'hidden',
      position: 'relative'
    }}>
      {/* Gradient overlay */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          right: 0,
          bottom: 0,
          left: 0,
          background:
            'radial-gradient(ellipse 77% 51% at 50% 130%, rgba(48,107,234,0.5) 0%, rgba(48,107,234,0) 80%), ' +
            'radial-gradient(ellipse 103% 70% at 50% 130%, rgba(48,107,234,0.3) 0%, rgba(48,107,234,0) 100%), ' +
            'radial-gradient(ellipse 112% 73% at 50% 130%, rgba(48,107,234,0.25) 0%, rgba(48,107,234,0) 100%)',
          zIndex: 0,
        }}
      />
      {/* Top Header with Debug/Deploy buttons */}
      <div style={{
        padding: '12px 20px',
        borderBottom: '1px solid #333',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        background: 'transparent',
        boxSizing: 'border-box',
        position: 'relative',
        zIndex: 1
      }}>
        {/* Top row: Logo + App Name | Buttons */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <img
              src="/fivetran-mark-white-rgb.png"
              alt="Fivetran"
              style={{
                height: '32px',
                filter: 'brightness(0.9)'
              }}
            />
            <h1 style={{ margin: 0, fontSize: '18px', fontWeight: '600' }}>{APP_NAME} <span style={{ fontSize: '11px', color: '#9b948f', fontWeight: 'normal' }}>(v{APP_VERSION})</span></h1>
          </div>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <span style={{ color: '#9b948f', fontSize: '12px' }}>{username}</span>
          <button
            onClick={handleLogout}
            style={{
              padding: '8px 16px',
              background: 'rgba(255, 255, 255, 0.1)',
              color: '#FDFCFB',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '12px',
              transition: 'all 0.2s ease'
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.2)'
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'
            }}
          >
            Logout
          </button>
        </div>
        </div>
        {/* Second row: Back arrow + Project name | Run + Deploy + Delete (centered) */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
          {/* Left: Home + Project name */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: '1' }}>
            <button
              onClick={handleNavigateHome}
              style={{
                background: 'transparent',
                border: '1px solid #444',
                borderRadius: '4px',
                color: '#9b948f',
                fontSize: '16px',
                cursor: 'pointer',
                padding: '6px',
                display: 'flex',
                alignItems: 'center',
                transition: 'all 0.2s ease'
              }}
              onMouseOver={(e) => { e.currentTarget.style.color = '#FDFCFB'; e.currentTarget.style.borderColor = '#666' }}
              onMouseOut={(e) => { e.currentTarget.style.color = '#9b948f'; e.currentTarget.style.borderColor = '#444' }}
              title="Home"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                <polyline points="9 22 9 12 15 12 15 22"></polyline>
              </svg>
            </button>
            <span style={{ fontSize: '16px', color: '#FDFCFB' }}>{projectName}</span>
          </div>
          {/* Center: Run + Deploy + Delete */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {/* Run Button */}
            <button
              onClick={debugLoading && debugAbortController ? stopDebug : handleDebug}
              disabled={loading || deployLoading || needsGeneration || (debugLoading && !debugAbortController)}
              style={{
                background: 'transparent',
                border: '1px solid #444',
                borderRadius: '4px',
                color: debugLoading && debugAbortController ? '#dc3545' : (debugLoading ? '#666' : '#9b948f'),
                cursor: (loading || deployLoading || needsGeneration || (debugLoading && !debugAbortController)) ? 'not-allowed' : 'pointer',
                padding: '6px',
                display: 'flex',
                alignItems: 'center',
                transition: 'all 0.2s ease',
                opacity: (loading || deployLoading || needsGeneration || (debugLoading && !debugAbortController)) ? 0.5 : 1
              }}
              onMouseOver={(e) => { if (!(loading || deployLoading || needsGeneration || (debugLoading && !debugAbortController))) { e.currentTarget.style.color = '#22c55e'; e.currentTarget.style.borderColor = '#22c55e' } }}
              onMouseOut={(e) => { e.currentTarget.style.color = debugLoading && debugAbortController ? '#dc3545' : (debugLoading ? '#666' : '#9b948f'); e.currentTarget.style.borderColor = '#444' }}
              title={debugLoading && debugAbortController ? 'Stop' : (debugLoading ? 'Running...' : (needsGeneration ? 'Generate connector first' : 'Debug Run'))}
            >
              {debugLoading && debugAbortController ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                  <rect x="6" y="6" width="12" height="12" rx="1"></rect>
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                  <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
              )}
            </button>
            {/* Deploy Button */}
            <button
              onClick={handleDeploy}
              disabled={needsGeneration || loading || debugLoading || deployLoading}
              style={{
                background: 'transparent',
                border: '1px solid #444',
                borderRadius: '4px',
                color: '#9b948f',
                cursor: (needsGeneration || loading || debugLoading || deployLoading) ? 'not-allowed' : 'pointer',
                padding: '6px',
                display: 'flex',
                alignItems: 'center',
                transition: 'all 0.2s ease',
                opacity: (needsGeneration || loading || debugLoading || deployLoading) ? 0.5 : 1
              }}
              onMouseOver={(e) => { if (!(needsGeneration || loading || debugLoading || deployLoading)) { e.currentTarget.style.color = '#306BEA'; e.currentTarget.style.borderColor = '#306BEA' } }}
              onMouseOut={(e) => { e.currentTarget.style.color = '#9b948f'; e.currentTarget.style.borderColor = '#444' }}
              title={needsGeneration ? 'Generate connector first' : 'Deploy'}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"></path>
                <path d="M12 12v9"></path>
                <path d="m16 16-4-4-4 4"></path>
              </svg>
            </button>
            {/* Download Button */}
            <button
              onClick={handleDownloadProject}
              disabled={needsGeneration || loading || debugLoading || deployLoading}
              style={{
                background: 'transparent',
                border: '1px solid #444',
                borderRadius: '4px',
                color: '#9b948f',
                cursor: (needsGeneration || loading || debugLoading || deployLoading) ? 'not-allowed' : 'pointer',
                padding: '6px',
                display: 'flex',
                alignItems: 'center',
                transition: 'all 0.2s ease',
                opacity: (needsGeneration || loading || debugLoading || deployLoading) ? 0.5 : 1
              }}
              onMouseOver={(e) => { if (!(needsGeneration || loading || debugLoading || deployLoading)) { e.currentTarget.style.color = '#306BEA'; e.currentTarget.style.borderColor = '#306BEA' } }}
              onMouseOut={(e) => { e.currentTarget.style.color = '#9b948f'; e.currentTarget.style.borderColor = '#444' }}
              title={needsGeneration ? 'Generate connector first' : 'Download Project'}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
            </button>
            {/* Reset State Button */}
            <button
              onClick={handleResetProject}
              disabled={loading || debugLoading || deployLoading}
              style={{
                background: 'transparent',
                border: '1px solid #444',
                borderRadius: '4px',
                color: '#9b948f',
                cursor: (loading || debugLoading || deployLoading) ? 'not-allowed' : 'pointer',
                padding: '6px',
                display: 'flex',
                alignItems: 'center',
                transition: 'all 0.2s ease',
                opacity: (loading || debugLoading || deployLoading) ? 0.5 : 1
              }}
              onMouseOver={(e) => { if (!(loading || debugLoading || deployLoading)) { e.currentTarget.style.color = '#f59e0b'; e.currentTarget.style.borderColor = '#f59e0b' } }}
              onMouseOut={(e) => { e.currentTarget.style.color = '#9b948f'; e.currentTarget.style.borderColor = '#444' }}
              title="Reset Sync State"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 2v6h-6"></path>
                <path d="M3 12a9 9 0 0 1 15-6.7L21 8"></path>
                <path d="M3 22v-6h6"></path>
                <path d="M21 12a9 9 0 0 1-15 6.7L3 16"></path>
              </svg>
            </button>
            {/* Delete Button */}
            <button
              onClick={handleDeleteConnector}
              disabled={loading || debugLoading || deployLoading}
              style={{
                background: 'transparent',
                border: '1px solid #444',
                borderRadius: '4px',
                color: '#9b948f',
                cursor: (loading || debugLoading || deployLoading) ? 'not-allowed' : 'pointer',
                padding: '6px',
                display: 'flex',
                alignItems: 'center',
                transition: 'all 0.2s ease',
                opacity: (loading || debugLoading || deployLoading) ? 0.5 : 1
              }}
              onMouseOver={(e) => { if (!(loading || debugLoading || deployLoading)) { e.currentTarget.style.color = '#dc3545'; e.currentTarget.style.borderColor = '#dc3545' } }}
              onMouseOut={(e) => { e.currentTarget.style.color = '#9b948f'; e.currentTarget.style.borderColor = '#444' }}
              title="Delete Connector"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                <line x1="10" y1="11" x2="10" y2="17"></line>
                <line x1="14" y1="11" x2="14" y2="17"></line>
              </svg>
            </button>
          </div>
          {/* Right spacer for balance */}
          <div style={{ flex: '1' }}></div>
        </div>
      </div>

      {/* Main Content Area */}
      <div style={{ 
        flex: 1, 
        display: 'flex', 
        overflow: 'hidden',
        background: 'transparent',
        position: 'relative',
        zIndex: 1
      }}>
      {/* Left Panel - Chat */}
      <div style={{
        width: showRightPanel ? `${leftPanelWidth}%` : 'calc(100% - 28px)',
        display: 'flex',
        flexDirection: 'column',
        background: 'rgba(26, 26, 26, 0.3)',
        backdropFilter: 'blur(10px)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        height: '100%',
        transition: 'width 0.3s ease',
        flexShrink: 0
      }}>

        {/* Chat Messages */}
        <div id="chat-container" style={{ flex: 1, padding: '20px', overflowY: 'auto', overflowX: 'hidden', background: 'rgba(26, 26, 26, 0.2)' }}>
          {/* Collapsible Spec Section */}
          {projectDescription && (
            <div style={{
              marginBottom: '16px',
              borderRadius: '8px',
              border: '1px solid #333',
              backgroundColor: 'rgba(42, 42, 42, 0.5)',
              overflow: 'hidden'
            }}>
              <div
                onClick={() => setSpecExpanded(!specExpanded)}
                style={{
                  padding: '10px 14px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  cursor: 'pointer',
                  color: '#9b948f',
                  fontSize: '12px',
                  fontWeight: '500'
                }}
              >
                <span style={{
                  fontSize: '10px',
                  transition: 'transform 0.2s ease',
                  transform: specExpanded ? 'rotate(90deg)' : 'rotate(0deg)'
                }}>
                  ▶
                </span>
                <span>Connector Spec</span>
              </div>
              {specExpanded && (
                <div style={{
                  padding: '0 14px 14px 14px',
                  fontSize: '13px',
                  color: '#FDFCFB',
                  lineHeight: '1.5',
                  borderTop: '1px solid #333'
                }}>
                  <div style={{ paddingTop: '12px' }}>
                    <ReactMarkdown
                      components={{
                        p: ({node, ...props}) => <p style={{ color: '#FDFCFB', margin: '0 0 8px 0' }} {...props} />,
                        strong: ({node, ...props}) => <strong style={{ color: '#FDFCFB', fontWeight: 'bold' }} {...props} />,
                        em: ({node, ...props}) => <em style={{ color: '#9b948f', fontStyle: 'italic' }} {...props} />,
                        li: ({node, ...props}) => <li style={{ color: '#FDFCFB', marginBottom: '4px', listStylePosition: 'outside' }} {...props} />,
                        ul: ({node, ...props}) => <ul style={{ color: '#FDFCFB', margin: '8px 0', paddingLeft: '28px', listStyleType: 'disc' }} {...props} />,
                        ol: ({node, ...props}) => <ol style={{ color: '#FDFCFB', margin: '8px 0', paddingLeft: '28px', listStyleType: 'decimal' }} {...props} />,
                        h1: ({node, ...props}) => <h1 style={{ color: '#FDFCFB', fontSize: '16px', fontWeight: 'bold', margin: '16px 0 8px 0' }} {...props} />,
                        h2: ({node, ...props}) => <h2 style={{ color: '#FDFCFB', fontSize: '14px', fontWeight: 'bold', margin: '12px 0 8px 0' }} {...props} />,
                        h3: ({node, ...props}) => <h3 style={{ color: '#FDFCFB', fontSize: '13px', fontWeight: 'bold', margin: '10px 0 6px 0' }} {...props} />,
                        code: ({node, ...props}) => <code style={{ color: '#FDFCFB', backgroundColor: 'rgba(255, 255, 255, 0.1)', padding: '2px 4px', borderRadius: '3px', fontSize: '12px' }} {...props} />,
                        pre: ({node, ...props}) => <pre style={{ backgroundColor: 'rgba(0, 0, 0, 0.3)', padding: '12px', borderRadius: '6px', overflow: 'auto', margin: '8px 0' }} {...props} />,
                        a: ({node, ...props}) => <a style={{ color: '#306BEA', textDecoration: 'underline' }} {...props} />,
                        blockquote: ({node, ...props}) => <blockquote style={{ borderLeft: '3px solid #444', paddingLeft: '12px', margin: '8px 0', color: '#9b948f' }} {...props} />
                      }}
                    >
                      {projectDescription}
                    </ReactMarkdown>
                  </div>
                </div>
              )}
            </div>
          )}
          {chatMessages.map((msg, index) => (
            <div key={`${msg.type}-${index}-${msg.timestamp}`} style={{ marginBottom: '16px' }}>
              {msg.type === 'user' ? (
                <div style={{
                  padding: '12px 16px',
                  borderRadius: '12px',
                  backgroundColor: '#2a2a2a',
                  color: '#FDFCFB',
                  maxWidth: '85%',
                  marginLeft: 'auto',
                  marginRight: '0',
                  fontSize: '14px',
                  lineHeight: '20px',
                  border: '1px solid #333',
                }}>
                  <ReactMarkdown
                    components={{
                      p: ({ children }) => <p style={{ margin: '0 0 8px 0' }}>{children}</p>,
                      strong: ({ children }) => <strong style={{ color: '#FDFCFB' }}>{children}</strong>,
                      em: ({ children }) => <em style={{ color: '#9b948f' }}>{children}</em>,
                    }}
                  >
                    {msg.text}
                  </ReactMarkdown>
                </div>
              ) : (
                <div style={{
                  padding: '12px 16px',
                  borderRadius: '12px',
                  backgroundColor: 'transparent',
                  color: '#FDFCFB',
                  maxWidth: '85%',
                  marginLeft: '0',
                  marginRight: 'auto',
                  fontSize: '14px',
                  lineHeight: '20px',
                }}>
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      p: ({ children }) => <p style={{ margin: '0 0 8px 0' }}>{children}</p>,
                      h1: ({ children }) => <h1 style={{ color: '#FDFCFB', fontSize: '16px', fontWeight: 'bold', margin: '16px 0 8px 0' }}>{children}</h1>,
                      h2: ({ children }) => <h2 style={{ color: '#FDFCFB', fontSize: '15px', fontWeight: 'bold', margin: '12px 0 8px 0' }}>{children}</h2>,
                      h3: ({ children }) => <h3 style={{ color: '#FDFCFB', fontSize: '14px', fontWeight: 'bold', margin: '10px 0 6px 0' }}>{children}</h3>,
                      code: ({ children }) => (
                        <code style={{
                          background: '#2a2a2a',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontSize: '12px',
                          fontFamily: 'monospace'
                        }}>
                          {children}
                        </code>
                      ),
                      pre: ({ children }) => (
                        <pre style={{
                          background: '#2a2a2a',
                          padding: '12px',
                          borderRadius: '6px',
                          overflow: 'auto',
                          fontSize: '12px',
                          fontFamily: 'monospace',
                          margin: '8px 0'
                        }}>
                          {children}
                        </pre>
                      ),
                      ul: ({ children }) => <ul style={{ margin: '8px 0', paddingLeft: '20px' }}>{children}</ul>,
                      ol: ({ children }) => <ol style={{ margin: '8px 0', paddingLeft: '20px' }}>{children}</ol>,
                      li: ({ children }) => <li style={{ margin: '4px 0' }}>{children}</li>,
                      strong: ({ children }) => <strong style={{ color: '#FDFCFB' }}>{children}</strong>,
                      em: ({ children }) => <em style={{ color: '#9b948f' }}>{children}</em>,
                    }}
                  >
                    {msg.text}
                  </ReactMarkdown>
                </div>
              )}
              {msg.type === 'ai' && msg.responseTime > 0 && (
                <div style={{
                  fontSize: '12px',
                  color: '#9b948f',
                  marginTop: '8px',
                  fontStyle: 'italic'
                }}>
                  Thought for {msg.responseTime} second{msg.responseTime !== 1 ? 's' : ''}
                </div>
              )}
            </div>
          ))}
          {needsGeneration && !loading && (
            <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'flex-end' }}>
              <button
                onClick={() => sendInitialGenerationMessage()}
                style={{
                  padding: '12px 24px',
                  background: '#306BEA',
                  color: '#FDFCFB',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: 'bold'
                }}
              >
                Generate Connector
              </button>
            </div>
          )}
          {loading && (
            <div style={{ marginBottom: '16px' }}>
              <div style={{
                padding: '12px 16px',
                borderRadius: '12px',
                backgroundColor: 'transparent',
                color: '#FDFCFB',
                maxWidth: '85%',
                marginLeft: '0',
                marginRight: 'auto',
                fontSize: '14px',
                lineHeight: '20px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                <div style={{
                  display: 'flex',
                  gap: '4px'
                }}>
                  <div style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: '#9b948f',
                    animation: 'typing 1.4s infinite ease-in-out'
                  }}></div>
                  <div style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: '#9b948f',
                    animation: 'typing 1.4s infinite ease-in-out 0.2s'
                  }}></div>
                  <div style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: '#9b948f',
                    animation: 'typing 1.4s infinite ease-in-out 0.4s'
                  }}></div>
                </div>
                <span style={{ color: '#9b948f', fontSize: '12px' }}>Working...</span>
              </div>
            </div>
          )}
          {/* AI Fix button - shown in chat when debug fails */}
          {pendingAIFixLogs && !aiFixLoading && !loading && (
            <div style={{ marginBottom: '16px' }}>
              <div style={{
                padding: '16px',
                borderRadius: '12px',
                backgroundColor: '#1a1a2e',
                border: '1px solid #306BEA',
                maxWidth: '85%',
                marginLeft: '0',
                marginRight: 'auto',
              }}>
                <div style={{
                  color: '#9b948f',
                  fontSize: '14px',
                  marginBottom: '12px',
                  lineHeight: '20px'
                }}>
                  🤖 Debug failed. Would you like AI to analyze the logs and attempt to fix the issue?
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                  <button
                    onClick={() => setPendingAIFixLogs(null)}
                    style={{
                      background: 'transparent',
                      color: '#9b948f',
                      border: '1px solid #444',
                      borderRadius: '6px',
                      padding: '10px 20px',
                      cursor: 'pointer',
                      fontSize: '14px',
                      fontWeight: 500
                    }}
                    onMouseOver={(e) => {
                      e.currentTarget.style.borderColor = '#666'
                      e.currentTarget.style.color = '#FDFCFB'
                    }}
                    onMouseOut={(e) => {
                      e.currentTarget.style.borderColor = '#444'
                      e.currentTarget.style.color = '#9b948f'
                    }}
                  >
                    Dismiss
                  </button>
                  <button
                    onClick={triggerAIFix}
                    style={{
                      background: '#306BEA',
                      color: '#fff',
                      border: 'none',
                      borderRadius: '6px',
                      padding: '10px 20px',
                      cursor: 'pointer',
                      fontSize: '14px',
                      fontWeight: 500
                    }}
                  >
                    Accept
                  </button>
                </div>
              </div>
            </div>
          )}
          {/* AI Fix loading indicator in chat */}
          {aiFixLoading && (
            <div style={{ marginBottom: '16px' }}>
              <div style={{
                padding: '12px 16px',
                borderRadius: '12px',
                backgroundColor: 'transparent',
                color: '#FDFCFB',
                maxWidth: '85%',
                marginLeft: '0',
                marginRight: 'auto',
                fontSize: '14px',
                lineHeight: '20px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                <div style={{
                  display: 'flex',
                  gap: '4px'
                }}>
                  <div style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: '#306BEA',
                    animation: 'typing 1.4s infinite ease-in-out'
                  }}></div>
                  <div style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: '#306BEA',
                    animation: 'typing 1.4s infinite ease-in-out 0.2s'
                  }}></div>
                  <div style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: '#306BEA',
                    animation: 'typing 1.4s infinite ease-in-out 0.4s'
                  }}></div>
                </div>
                <span style={{ color: '#306BEA', fontSize: '12px' }}>AI is analyzing and fixing...</span>
              </div>
            </div>
          )}
        </div>

        {/* Chat Input */}
        <div style={{ padding: '16px', borderTop: '1px solid #333', background: 'rgba(26, 26, 26, 0.2)' }}>
          
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <input
              type="text"
              placeholder="Ask a follow-up"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
              disabled={loading}
              style={{
                flex: 1,
                padding: '12px 16px',
                background: '#2a2a2a',
                border: '1px solid #444',
                borderRadius: '8px',
                color: '#FDFCFB',
                fontSize: '14px',
                opacity: loading ? 0.6 : 1,
                outline: 'none'
              }}
            />
            {(() => {
              // Show stop button only when operation is active AND we have an abort controller
              return (loading && abortController) || stopping
            })() ? (
              <button
                onClick={() => {
                  if (!stopping) stopGeneration()
                }}
                disabled={stopping}
                style={{
                  width: '36px',
                  height: '36px',
                  background: stopping ? '#666' : '#dc3545',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: stopping ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '12px',
                  color: '#FDFCFB',
                  transition: 'all 0.2s ease',
                  fontWeight: 'bold',
                  opacity: stopping ? 0.7 : 1
                }}
                title={stopping ? "Stopping..." : "Stop operation"}
              >
                {stopping ? '...' : '⏹'}
              </button>
            ) : (
              <button 
                onClick={sendMessage}
                disabled={loading || !chatInput.trim()}
                style={{ 
                  width: '36px',
                  height: '36px',
                  background: loading || !chatInput.trim() ? '#666' : '#306BEA', 
                  border: 'none', 
                  borderRadius: '6px', 
                  cursor: loading || !chatInput.trim() ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '16px',
                  color: '#FDFCFB',
                  transition: 'all 0.2s ease'
                }}
                title="Send message (smart routing)"
              >
                {loading ? '...' : '↑'}
              </button>
            )}
          </div>
        </div>

      </div>

      {/* Toggle right panel button - positioned at the edge */}
      <button
        onClick={() => setShowRightPanel(!showRightPanel)}
        style={{
          background: showRightPanel ? 'rgba(48, 107, 234, 0.2)' : 'rgba(42, 42, 42, 0.9)',
          border: '1px solid #444',
          borderRadius: showRightPanel ? '4px 0 0 4px' : '4px',
          color: showRightPanel ? '#306BEA' : '#9b948f',
          cursor: 'pointer',
          padding: '8px 4px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'all 0.2s ease',
          height: 'auto',
          alignSelf: 'center',
          flexShrink: 0
        }}
        onMouseOver={(e) => { e.currentTarget.style.color = '#FDFCFB'; e.currentTarget.style.borderColor = '#666'; e.currentTarget.style.background = 'rgba(48, 107, 234, 0.3)' }}
        onMouseOut={(e) => { e.currentTarget.style.color = showRightPanel ? '#306BEA' : '#9b948f'; e.currentTarget.style.borderColor = '#444'; e.currentTarget.style.background = showRightPanel ? 'rgba(48, 107, 234, 0.2)' : 'rgba(42, 42, 42, 0.9)' }}
        title={showRightPanel ? 'Hide Files & Logs' : 'Show Files & Logs'}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ transform: showRightPanel ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s ease' }}
        >
          <polyline points="15 18 9 12 15 6"></polyline>
        </svg>
      </button>

      {/* Resizer - only show when right panel is visible */}
      {showRightPanel && (
        <div
          onMouseDown={handleMouseDown}
          style={{
            width: '4px',
            background: isResizing ? '#306BEA' : '#333',
            cursor: 'col-resize',
            height: '100%',
            position: 'relative',
            transition: isResizing ? 'none' : 'background-color 0.2s ease',
            zIndex: 2
          }}
        />
      )}

      {/* Right Panel - Code Editor - only show when toggled */}
      {showRightPanel && (
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        background: 'rgba(26, 26, 26, 0.3)',
        backdropFilter: 'blur(10px)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        height: '100%',
        overflow: 'hidden'
      }}>

        {/* Tabs */}
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          gap: '8px',
          padding: '12px 16px',
          borderBottom: '1px solid #333',
          background: 'rgba(27, 24, 24, 0.4)'
        }}>
          <button
            className="tab-transition"
            onClick={() => setActiveTab('files')}
            style={{
              padding: '8px 16px',
              background: activeTab === 'files' ? 'rgba(48, 107, 234, 0.15)' : 'transparent',
              color: activeTab === 'files' ? '#FDFCFB' : '#9b948f',
              border: activeTab === 'files' ? '1px solid #306BEA' : '1px solid #444',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: '500',
              transition: 'all 0.2s ease',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
            onMouseOver={(e) => { if (activeTab !== 'files') { e.currentTarget.style.color = '#FDFCFB'; e.currentTarget.style.borderColor = '#666' } }}
            onMouseOut={(e) => { if (activeTab !== 'files') { e.currentTarget.style.color = '#9b948f'; e.currentTarget.style.borderColor = '#444' } }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
            Files
          </button>
          <button
            className="tab-transition"
            onClick={() => setActiveTab('logs')}
            style={{
              padding: '8px 16px',
              background: activeTab === 'logs' ? 'rgba(48, 107, 234, 0.15)' : 'transparent',
              color: activeTab === 'logs' ? '#FDFCFB' : '#9b948f',
              border: activeTab === 'logs' ? '1px solid #306BEA' : '1px solid #444',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: '500',
              transition: 'all 0.2s ease',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
            onMouseOver={(e) => { if (activeTab !== 'logs') { e.currentTarget.style.color = '#FDFCFB'; e.currentTarget.style.borderColor = '#666' } }}
            onMouseOut={(e) => { if (activeTab !== 'logs') { e.currentTarget.style.color = '#9b948f'; e.currentTarget.style.borderColor = '#444' } }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20h9"></path>
              <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"></path>
            </svg>
            Logs
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }} data-right-panel>
          {/* Files Tab */}
          <div className={activeTab === 'files' ? 'content-fade-in' : ''} style={{ display: activeTab === 'files' ? 'flex' : 'none', width: '100%', flexDirection: 'column' }}>
              {/* File Navbar */}
              <div style={{
                display: 'flex',
                gap: '12px',
                padding: '12px 16px',
                background: 'rgba(27, 24, 24, 0.4)',
                borderBottom: '1px solid #333',
                alignItems: 'center'
              }}>
                {/* File Selector Dropdown */}
                <span style={{ color: '#9b948f', fontSize: '12px', fontWeight: 500, whiteSpace: 'nowrap' }}>Files:</span>
                <select
                  value={selectedFile}
                  onChange={(e) => handleFileClick(e.target.value)}
                  style={{
                    padding: '8px 12px',
                    background: '#2a2a2a',
                    border: '1px solid #555',
                    borderRadius: '6px',
                    color: '#FDFCFB',
                    fontSize: '13px',
                    minWidth: '200px',
                    cursor: 'pointer'
                  }}
                >
                  {filteredFiles.map((file) => (
                    <option key={file.name} value={file.name}>
                      {file.name}
                    </option>
                  ))}
                </select>

                <div style={{ flex: 1 }} />
                {/* Search */}
                <input
                  type="text"
                  placeholder="Search files..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    padding: '8px 12px',
                    background: 'rgba(42, 42, 42, 0.3)',
                    border: '1px solid #444',
                    borderRadius: '6px',
                    color: '#FDFCFB',
                    fontSize: '12px',
                    width: '160px'
                  }}
                />

              </div>

              {/* Code Editor */}
              <div style={{ flex: 1, padding: '16px', background: 'rgba(27, 24, 24, 0.2)', height: '100%', overflow: 'hidden' }}>
                <div style={{ background: 'rgba(26, 26, 26, 0.2)', borderRadius: '6px', overflow: 'hidden', height: '100%' }}>
                  {/* Header panel - only show for non-database files */}
                  {selectedFile && !isDatabaseFile(selectedFile) && (
                    <div style={{ 
                      padding: '12px', 
                      background: 'rgba(42, 42, 42, 0.3)', 
                      borderBottom: '1px solid #333', 
                      fontSize: '12px', 
                      color: '#FDFCFB',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}>
                      <span>{selectedFile}</span>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        {isEditing ? (
                          <>
                            <button
                              onClick={handleSaveCode}
                              style={{
                                padding: '4px 12px',
                                background: '#306BEA',
                                color: '#FDFCFB',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer',
                                fontSize: '12px'
                              }}
                            >
                              Save
                            </button>
                            <button
                              onClick={handleCancelEdit}
                              style={{
                                padding: '4px 12px',
                                background: 'rgba(42, 42, 42, 0.3)',
                                color: '#FDFCFB',
                                border: '1px solid #444',
                                borderRadius: '4px',
                                cursor: 'pointer',
                                fontSize: '12px'
                              }}
                            >
                              Cancel
                            </button>
                          </>
                        ) : (selectedFile === 'configuration.json' && configDecryptFailed) ? null : (
                          <button
                            onClick={handleEditCode}
                            disabled={loading || debugLoading || deployLoading}
                            style={{
                              padding: '4px 12px',
                              background: 'rgba(42, 42, 42, 0.3)',
                              color: '#FDFCFB',
                              border: '1px solid #444',
                              borderRadius: '4px',
                              cursor: (loading || debugLoading || deployLoading) ? 'not-allowed' : 'pointer',
                              fontSize: '12px',
                              opacity: (loading || debugLoading || deployLoading) ? 0.5 : 1
                            }}
                          >
                            Edit
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                  <div className={filesLoading ? 'files-loading' : ''} style={{ height: isDatabaseFile(selectedFile) ? '100%' : 'calc(100% - 45px)', display: 'flex', flexDirection: 'column' }}>
                    {isDatabaseFile(selectedFile) ? (
                      <DatabaseViewer
                        username={localStorage.getItem('username') || ''}
                        projectName={localStorage.getItem('current_project_name') || ''}
                      />
                    ) : isMarkdownFile(selectedFile) && !isEditing ? (
                      <div style={{
                        height: '100%',
                        overflow: 'auto',
                        padding: '32px 48px',
                        background: '#1a1a1a',
                        color: '#FDFCFB'
                      }}>
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            h1: ({children}) => (
                              <h1 style={{
                                fontSize: '32px',
                                fontWeight: 'bold',
                                color: '#FDFCFB',
                                marginTop: '24px',
                                marginBottom: '16px',
                                borderBottom: '1px solid #444',
                                paddingBottom: '8px'
                              }}>{children}</h1>
                            ),
                            h2: ({children}) => (
                              <h2 style={{
                                fontSize: '24px',
                                fontWeight: 'bold',
                                color: '#FDFCFB',
                                marginTop: '20px',
                                marginBottom: '12px',
                                borderBottom: '1px solid #333',
                                paddingBottom: '6px'
                              }}>{children}</h2>
                            ),
                            h3: ({children}) => (
                              <h3 style={{
                                fontSize: '20px',
                                fontWeight: 'bold',
                                color: '#FDFCFB',
                                marginTop: '16px',
                                marginBottom: '10px'
                              }}>{children}</h3>
                            ),
                            h4: ({children}) => (
                              <h4 style={{
                                fontSize: '16px',
                                fontWeight: 'bold',
                                color: '#FDFCFB',
                                marginTop: '14px',
                                marginBottom: '8px'
                              }}>{children}</h4>
                            ),
                            p: ({children}) => (
                              <p style={{
                                color: '#FDFCFB',
                                margin: '0 0 12px 0',
                                lineHeight: '1.6',
                                fontSize: '14px'
                              }}>{children}</p>
                            ),
                            code: ({inline, children, ...props}: any) => (
                              inline ? (
                                <code style={{
                                  background: '#2a2a2a',
                                  color: '#6bcf7f',
                                  padding: '2px 6px',
                                  borderRadius: '3px',
                                  fontSize: '13px',
                                  fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace'
                                }} {...props}>{children}</code>
                              ) : (
                                <code style={{
                                  display: 'block',
                                  background: '#2a2a2a',
                                  color: '#FDFCFB',
                                  padding: '12px',
                                  borderRadius: '6px',
                                  fontSize: '13px',
                                  fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
                                  overflowX: 'auto',
                                  margin: '12px 0',
                                  lineHeight: '1.5'
                                }} {...props}>{children}</code>
                              )
                            ),
                            pre: ({children}) => (
                              <pre style={{
                                background: '#2a2a2a',
                                padding: '0',
                                borderRadius: '6px',
                                margin: '12px 0',
                                overflow: 'hidden'
                              }}>{children}</pre>
                            ),
                            ul: ({children}) => (
                              <ul style={{
                                color: '#FDFCFB',
                                margin: '8px 0',
                                paddingLeft: '24px',
                                lineHeight: '1.6'
                              }}>{children}</ul>
                            ),
                            ol: ({children}) => (
                              <ol style={{
                                color: '#FDFCFB',
                                margin: '8px 0',
                                paddingLeft: '24px',
                                lineHeight: '1.6'
                              }}>{children}</ol>
                            ),
                            li: ({children}) => (
                              <li style={{
                                color: '#FDFCFB',
                                marginBottom: '4px',
                                fontSize: '14px'
                              }}>{children}</li>
                            ),
                            strong: ({children}) => (
                              <strong style={{
                                color: '#FDFCFB',
                                fontWeight: 'bold'
                              }}>{children}</strong>
                            ),
                            em: ({children}) => (
                              <em style={{
                                color: '#9b948f',
                                fontStyle: 'italic'
                              }}>{children}</em>
                            ),
                            a: ({children, href}) => (
                              <a href={href} target="_blank" rel="noopener noreferrer" style={{
                                color: '#306BEA',
                                textDecoration: 'underline'
                              }}>{children}</a>
                            ),
                            blockquote: ({children}) => (
                              <blockquote style={{
                                borderLeft: '4px solid #306BEA',
                                paddingLeft: '16px',
                                margin: '12px 0',
                                color: '#9b948f',
                                fontStyle: 'italic'
                              }}>{children}</blockquote>
                            ),
                            table: ({children}) => (
                              <table style={{
                                borderCollapse: 'collapse',
                                width: '100%',
                                margin: '12px 0',
                                fontSize: '14px'
                              }}>{children}</table>
                            ),
                            thead: ({children}) => (
                              <thead style={{
                                background: '#2a2a2a',
                                borderBottom: '2px solid #444'
                              }}>{children}</thead>
                            ),
                            tbody: ({children}) => (
                              <tbody>{children}</tbody>
                            ),
                            tr: ({children}) => (
                              <tr style={{
                                borderBottom: '1px solid #333'
                              }}>{children}</tr>
                            ),
                            th: ({children}) => (
                              <th style={{
                                padding: '10px 12px',
                                textAlign: 'left',
                                color: '#FDFCFB',
                                fontWeight: 'bold'
                              }}>{children}</th>
                            ),
                            td: ({children}) => (
                              <td style={{
                                padding: '8px 12px',
                                color: '#FDFCFB'
                              }}>{children}</td>
                            ),
                            hr: () => (
                              <hr style={{
                                border: 'none',
                                borderTop: '1px solid #444',
                                margin: '20px 0'
                              }} />
                            )
                          }}
                        >
                          {codeContent || 'Select a file to view its content'}
                        </ReactMarkdown>
                      </div>
                    ) : selectedFile === 'configuration.json' && configDecryptFailed ? (
                      // Configuration encrypted by different user/system - show warning
                      <div style={{
                        flex: 1,
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: '32px',
                        backgroundColor: '#1a1a1a',
                        color: '#FDFCFB'
                      }}>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '12px',
                          marginBottom: '16px'
                        }}>
                          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#ffaa00" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                            <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                          </svg>
                          <span style={{ fontSize: '18px', fontWeight: '600', color: '#ffaa00' }}>
                            Configuration Inaccessible
                          </span>
                        </div>
                        <p style={{
                          color: '#9b948f',
                          fontSize: '14px',
                          textAlign: 'center',
                          maxWidth: '400px',
                          lineHeight: '1.6'
                        }}>
                          {configDecryptMessage || 'Configuration was encrypted by a different user or system.'}
                        </p>
                      </div>
                    ) : (
                      <div style={{ flex: 1, overflow: 'hidden' }}>
                        <Editor
                          height="100%"
                        language={selectedFile ? getLanguageFromFilename(selectedFile) : 'plaintext'}
                        value={codeContent || 'Select a file to view its content'}
                        onChange={(value) => {
                          if (isEditing && value !== undefined) {
                            // Content is being edited, but we don't need to update state here
                            // Monaco Editor handles its own state
                          }
                        }}
                        onMount={handleEditorDidMount}
                        options={{
                          readOnly: !isEditing || loading || debugLoading || deployLoading,
                          theme: 'vs-dark',
                          fontSize: 14,
                          lineHeight: 20,
                          fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',

                          // Basic UI
                          minimap: { enabled: true, side: 'right', showSlider: 'mouseover' },
                          scrollBeyondLastLine: false,
                          automaticLayout: true,
                          wordWrap: 'on',
                          lineNumbers: 'on',
                          glyphMargin: true,
                          folding: true,
                          lineDecorationsWidth: 0,
                          lineNumbersMinChars: 3,
                          renderLineHighlight: 'line',
                          cursorStyle: 'line',
                          cursorBlinking: 'blink',
                          selectOnLineNumbers: true,
                          roundedSelection: false,
                          contextmenu: true,
                          mouseWheelZoom: true,
                          smoothScrolling: true,
                          padding: { top: 20, bottom: 20 },

                          // IntelliSense & Auto-complete
                          quickSuggestions: true,
                          suggestOnTriggerCharacters: true,
                          acceptSuggestionOnEnter: 'on',
                          tabCompletion: 'on',
                          snippetSuggestions: 'top',

                          // Parameter hints & hover
                          parameterHints: { enabled: true },
                          hover: { enabled: true, delay: 300 },

                          // Formatting
                          formatOnPaste: true,
                          formatOnType: true,
                          autoIndent: 'full',

                          // Brackets & Quotes
                          bracketPairColorization: { enabled: true },
                          autoClosingBrackets: 'always',
                          autoClosingQuotes: 'always',
                          autoSurround: 'languageDefined',

                          // Navigation
                          breadcrumbs: { enabled: true },
                          stickyScroll: { enabled: true },
                          links: true,

                          // Multi-cursor
                          multiCursorModifier: 'alt',
                          multiCursorPaste: 'spread',

                          // Visual enhancements
                          occurrencesHighlight: 'singleFile',
                          codeLens: true,
                          renameOnType: true,

                          // Unicode & special characters
                          unicodeHighlight: { ambiguousCharacters: true },

                          scrollbar: {
                            vertical: 'auto',
                            horizontal: 'auto',
                            useShadows: false,
                            verticalHasArrows: false,
                            horizontalHasArrows: false,
                            verticalScrollbarSize: 12,
                            horizontalScrollbarSize: 12
                          }
                        }}
                        />
                      </div>
                    )}
                  </div>
                </div>
              </div>
          </div>
          
          {/* Logs Tab */}
          <div className="content-fade-in" style={{ display: activeTab === 'logs' ? 'flex' : 'none', flex: 1, padding: '16px', background: '#1B1818', height: '100%', overflow: 'hidden', flexDirection: 'column' }}>
              <div id="debug-logs-scrollable" style={{ background: '#1a1a1a', borderRadius: '6px', padding: '20px', flex: 1, overflow: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
                <div 
                  id="logs-container"
                  style={{ fontSize: '14px', color: '#9b948f', fontFamily: 'monospace', lineHeight: '24px', minHeight: '100%' }}
                >
                  {logs.length === 0 ? (
                    <div style={{ color: '#666', fontStyle: 'italic' }}>
                      No logs yet. Click the Debug button to start debugging...
                    </div>
                  ) : (
                    logs.map((log, index) => (
                      <div key={index} style={{
                        color: log.level === 'ERROR' ? '#ff6b6b' :
                               log.level === 'WARNING' ? '#ffd93d' :
                               log.level === 'INFO' ? '#6bcf7f' : '#9b948f',
                        marginBottom: '4px'
                      }}>
                        [{log.timestamp}] {log.level}: {log.message}
                      </div>
                    ))
                  )}
                </div>
              </div>
          </div>
        </div>
      </div>
      )}
      </div>

      {/* Deploy Dialog */}
      {showDeployDialog && (
        <div className="modal-backdrop" style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div className="modal-content" style={{
            backgroundColor: '#1B1818',
            borderRadius: '12px',
            padding: '24px',
            width: '500px',
            maxWidth: '90vw',
            border: '1px solid #333'
          }}>
            {/* Header with close button */}
            <div style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center',
              marginBottom: '20px'
            }}>
              <h2 style={{ 
                margin: '0', 
                color: '#FDFCFB', 
                fontSize: '18px',
                fontWeight: '600'
              }}>
                Deploy Connector
              </h2>
              <button
                onClick={handleDeployCancel}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#9b948f',
                  fontSize: '20px',
                  cursor: 'pointer',
                  padding: '4px',
                  borderRadius: '4px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '28px',
                  height: '28px'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = '#333'
                  e.currentTarget.style.color = '#FDFCFB'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent'
                  e.currentTarget.style.color = '#9b948f'
                }}
              >
                ×
              </button>
            </div>
            
            {/* Error Message */}
            {deployError && (
              <div style={{
                backgroundColor: '#2d1b1b',
                border: '1px solid #ff6b6b',
                borderRadius: '6px',
                padding: '12px',
                marginBottom: '20px',
                color: '#ff6b6b',
                fontSize: '14px'
              }}>
                ⚠️ {deployError}
              </div>
            )}
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Connector Name */}
              <div>
                <label style={{ 
                  display: 'block', 
                  marginBottom: '6px', 
                  color: '#FDFCFB', 
                  fontSize: '14px',
                  fontWeight: '500'
                }}>
                  Connector Name
                </label>
                <input
                  type="text"
                  value={deployForm.connectorName}
                  onChange={(e) => {
                    const value = e.target.value
                    setDeployForm(prev => ({ ...prev, connectorName: value }))

                    // Validate connector name format
                    const error = validateProjectName(value, [])
                    if (error) {
                      setDeployError(error)
                    } else {
                      setDeployError('')
                    }
                  }}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    backgroundColor: '#2a2a2a',
                    border: '1px solid #444',
                    borderRadius: '6px',
                    color: '#FDFCFB',
                    fontSize: '14px',
                    boxSizing: 'border-box'
                  }}
                  placeholder="Enter connector name"
                />
              </div>

              {/* Destination Name */}
              <div>
                <label style={{ 
                  display: 'block', 
                  marginBottom: '6px', 
                  color: '#FDFCFB', 
                  fontSize: '14px',
                  fontWeight: '500'
                }}>
                  Destination Name
                </label>
                <input
                  type="text"
                  value={deployForm.destinationName}
                  onChange={(e) => {
                    setDeployForm(prev => ({ ...prev, destinationName: e.target.value }))
                    // Clear error when user starts typing
                    if (deployError && e.target.value.trim()) {
                      setDeployError('')
                    }
                  }}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    backgroundColor: '#2a2a2a',
                    border: '1px solid #444',
                    borderRadius: '6px',
                    color: '#FDFCFB',
                    fontSize: '14px',
                    boxSizing: 'border-box'
                  }}
                  placeholder="Enter destination name"
                />
              </div>

              {/* API Key */}
              <div>
                <label style={{
                  display: 'block',
                  marginBottom: '6px',
                  color: '#FDFCFB',
                  fontSize: '14px',
                  fontWeight: '500'
                }}>
                  Base64-encoded API key
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    value={deployForm.apiKey}
                    onChange={(e) => {
                      setDeployForm(prev => ({ ...prev, apiKey: e.target.value }))
                      // Clear error when user starts typing
                      if (deployError && e.target.value.trim()) {
                        setDeployError('')
                      }
                    }}
                    placeholder="Enter your API key"
                    style={{
                      width: '100%',
                      padding: '10px 45px 10px 12px',
                      backgroundColor: '#2a2a2a',
                      border: '1px solid #444',
                      borderRadius: '6px',
                      color: '#FDFCFB',
                      fontSize: '14px',
                      boxSizing: 'border-box'
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    style={{
                      position: 'absolute',
                      right: '12px',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      background: 'none',
                      border: 'none',
                      color: '#9b948f',
                      cursor: 'pointer',
                      padding: '4px',
                      fontSize: '16px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.color = '#FDFCFB'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.color = '#9b948f'
                    }}
                  >
                    {showApiKey ? '🙈' : '👀'}
                  </button>
                </div>
              </div>

              {/* Include Configuration.json */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="checkbox"
                  id="includeConfig"
                  checked={deployForm.includeConfig}
                  onChange={(e) => setDeployForm(prev => ({ ...prev, includeConfig: e.target.checked }))}
                  style={{
                    width: '16px',
                    height: '16px',
                    accentColor: '#306BEA'
                  }}
                />
                <label htmlFor="includeConfig" style={{ 
                  color: '#FDFCFB', 
                  fontSize: '14px',
                  cursor: 'pointer'
                }}>
                  Include configuration.json
                </label>
              </div>

              {/* Force Deployment */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="checkbox"
                  id="forceDeployment"
                  checked={deployForm.forceDeployment}
                  onChange={(e) => setDeployForm(prev => ({ ...prev, forceDeployment: e.target.checked }))}
                  style={{
                    width: '16px',
                    height: '16px',
                    accentColor: '#306BEA'
                  }}
                />
                <label htmlFor="forceDeployment" style={{ 
                  color: '#FDFCFB', 
                  fontSize: '14px',
                  cursor: 'pointer'
                }}>
                  Force deployment
                </label>
              </div>
            </div>

            {/* Buttons */}
            <div style={{ 
              display: 'flex', 
              gap: '12px', 
              marginTop: '24px',
              justifyContent: 'flex-end'
            }}>
              <button
                onClick={handleDeploySubmit}
                disabled={deployLoading}
                style={{
                  padding: '10px 20px',
                  backgroundColor: deployLoading ? '#1a1a1a' : '#306BEA',
                  color: deployLoading ? '#FDFCFB' : '#FDFCFB',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: deployLoading ? 'not-allowed' : 'pointer',
                  fontSize: '14px',
                  opacity: deployLoading ? 0.8 : 1,
                  position: 'relative',
                  overflow: 'hidden',
                  width: '120px',
                  height: '40px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  transition: 'all 0.2s ease'
                }}
              >
                {deployLoading && (
                  <div style={{
                    position: 'absolute',
                    top: 0,
                    left: '-100%',
                    width: '100%',
                    height: '100%',
                    background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent)',
                    animation: 'shimmer 2s infinite'
                  }} />
                )}
                <span style={{ 
                  position: 'relative', 
                  zIndex: 1,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}>
                  {deployLoading && (
                    <div style={{
                      width: '12px',
                      height: '12px',
                      border: '2px solid #FDFCFB',
                      borderTop: '2px solid transparent',
                      borderRadius: '50%',
                      animation: 'spin 1s linear infinite'
                    }} />
                  )}
                  {deployLoading ? 'Deploying...' : 'Deploy'}
                </span>
              </button>
            </div>
            
            {/* Deploy Logs Section - moved to bottom */}
            {deployLogs.length > 0 && (
              <div
                ref={deployLogsRef}
                style={{
                  backgroundColor: '#1a1a1a',
                  borderRadius: '6px',
                  padding: '12px',
                  marginTop: '20px',
                  maxHeight: '200px',
                  overflowY: 'auto',
                  border: deployStatus === 'failed'
                    ? '2px solid #ff6b6b'  // Red border on failure
                    : deployStatus === 'success'
                    ? '2px solid #6bcf7f'  // Green border on success
                    : '1px solid #333'     // Gray border default
                }}>
                <div style={{ 
                  fontSize: '12px', 
                  color: '#9b948f', 
                  fontFamily: 'monospace', 
                  lineHeight: '18px' 
                }}>
                  {deployLogs.map((log, index) => (
                    <div key={index} style={{ 
                      color: log.level === 'ERROR' ? '#ff6b6b' : 
                             log.level === 'WARNING' ? '#ffd93d' : 
                             log.level === 'INFO' ? '#6bcf7f' : '#9b948f'
                    }}>
                      [{log.timestamp}] {log.level}: {log.message}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Delete File Confirmation Dialog */}
      {showDeleteDialog && (
        <div className="modal-backdrop" style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div className="modal-content" style={{
            backgroundColor: '#1b1818',
            border: '1px solid #444',
            borderRadius: '8px',
            padding: '24px',
            minWidth: '400px',
            maxWidth: '500px'
          }}>
            <h3 style={{ 
              color: '#FDFCFB', 
              margin: '0 0 16px 0', 
              fontSize: '18px',
              fontWeight: '600'
            }}>
              Delete File
            </h3>
            
            <p style={{ 
              color: '#bdb7b2', 
              marginBottom: '20px', 
              lineHeight: '1.5' 
            }}>
              Are you sure you want to delete <strong style={{color: '#FDFCFB'}}>{fileToDelete}</strong>?
              <br />
              <span style={{color: '#ff6b6b', fontSize: '14px'}}>This action cannot be undone.</span>
            </p>

            <div style={{ 
              display: 'flex', 
              gap: '12px', 
              justifyContent: 'flex-end' 
            }}>
              <button
                onClick={cancelDeleteFile}
                disabled={deleteLoading}
                style={{
                  padding: '10px 20px',
                  background: '#333',
                  color: '#FDFCFB',
                  border: '1px solid #555',
                  borderRadius: '6px',
                  cursor: deleteLoading ? 'not-allowed' : 'pointer',
                  opacity: deleteLoading ? 0.5 : 1
                }}
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteFile}
                disabled={deleteLoading}
                style={{
                  padding: '10px 20px',
                  background: '#ff6b6b',
                  color: '#FDFCFB',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: deleteLoading ? 'not-allowed' : 'pointer',
                  opacity: deleteLoading ? 0.5 : 1
                }}
              >
                {deleteLoading ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reset Project Confirmation Dialog */}
      {showResetDialog && (
        <div className="modal-backdrop" style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div className="modal-content" style={{
            backgroundColor: '#1b1818',
            border: '1px solid #444',
            borderRadius: '8px',
            padding: '24px',
            minWidth: '400px',
            maxWidth: '500px'
          }}>
            <h3 style={{
              color: '#FDFCFB',
              margin: '0 0 16px 0',
              fontSize: '18px',
              fontWeight: '600'
            }}>
              Reset Fivetran Sync State
            </h3>

            <p style={{
              color: '#bdb7b2',
              marginBottom: '16px',
              lineHeight: '1.5'
            }}>
              This will delete the <strong style={{color: '#FDFCFB'}}>files/</strong> directory (warehouse.db, state files).
              <br />
              <br />
              <span style={{color: '#ff6b6b', fontSize: '14px'}}>This action cannot be undone.</span>
            </p>

            <label style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              color: '#bdb7b2',
              cursor: 'pointer',
              marginBottom: '20px',
              padding: '12px',
              backgroundColor: '#252222',
              borderRadius: '6px',
              border: '1px solid #333'
            }}>
              <input
                type="checkbox"
                checked={resetDeleteVenv}
                onChange={(e) => setResetDeleteVenv(e.target.checked)}
                style={{
                  width: '18px',
                  height: '18px',
                  cursor: 'pointer',
                  accentColor: '#ff6b6b'
                }}
              />
              <span>
                Also delete <strong style={{color: '#FDFCFB'}}>venv/</strong> directory (~50-200MB)
                <br />
                <span style={{color: '#86807B', fontSize: '12px'}}>
                  Will be recreated automatically on next test/debug
                </span>
              </span>
            </label>

            <div style={{
              display: 'flex',
              gap: '12px',
              justifyContent: 'flex-end'
            }}>
              <button
                onClick={cancelResetProject}
                disabled={resetLoading}
                style={{
                  padding: '10px 20px',
                  background: '#333',
                  color: '#FDFCFB',
                  border: '1px solid #555',
                  borderRadius: '6px',
                  cursor: resetLoading ? 'not-allowed' : 'pointer',
                  opacity: resetLoading ? 0.5 : 1
                }}
              >
                Cancel
              </button>
              <button
                onClick={confirmResetProject}
                disabled={resetLoading}
                style={{
                  padding: '10px 20px',
                  background: '#ff6b6b',
                  color: '#FDFCFB',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: resetLoading ? 'not-allowed' : 'pointer',
                  opacity: resetLoading ? 0.5 : 1
                }}
              >
                {resetLoading ? 'Resetting...' : 'Reset'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Configuration Review Modal */}
      {showConfigReview && (
        <div className="modal-backdrop" style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div className="modal-content" style={{
            backgroundColor: '#1B1818',
            borderRadius: '12px',
            padding: '24px',
            width: '500px',
            maxWidth: '90vw',
            maxHeight: '80vh',
            overflow: 'auto',
            border: '1px solid #333'
          }}>
            {/* Header with close button */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '20px'
            }}>
              <h2 style={{
                margin: '0',
                color: '#FDFCFB',
                fontSize: '18px',
                fontWeight: '600'
              }}>
                Secure Configuration Entry
              </h2>
              <button
                disabled={cancellingConfig}
                onClick={async () => {
                  if (cancellingConfig) return

                  // Show immediate feedback
                  setCancellingConfig(true)

                  // Send cancel request to backend with timeout
                  const projectName = localStorage.getItem('current_project_name')

                  if (projectName) {
                    try {
                      const controller = new AbortController()
                      const timeoutId = setTimeout(() => controller.abort(), 3000) // 3 second timeout

                      await authenticatedFetch(`${API_BASE}/cancel-config`, {
                        method: 'POST',
                        headers: {
                          'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ project_name: projectName }),
                        signal: controller.signal
                      })
                      clearTimeout(timeoutId)
                    } catch (error) {
                      console.warn('Cancel config request failed:', error)
                    }
                  }

                  // Close dialog and clean up
                  setShowConfigReview(false)
                  setVisibleSensitiveFields(new Set())
                  setConfigContext(null)
                  setCancellingConfig(false)
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: cancellingConfig ? '#666' : '#9b948f',
                  fontSize: '20px',
                  cursor: cancellingConfig ? 'wait' : 'pointer',
                  padding: '4px',
                  borderRadius: '4px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '28px',
                  height: '28px',
                  opacity: cancellingConfig ? 0.5 : 1
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = '#333'
                  e.currentTarget.style.color = '#FDFCFB'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent'
                  e.currentTarget.style.color = '#9b948f'
                }}
              >
                ×
              </button>
            </div>

            {/* Subheading */}
            <p style={{
              color: '#9b948f',
              fontSize: '13px',
              lineHeight: '1.5',
              margin: '0 0 20px 0'
            }}>
              Provide configuration values. They are stored encrypted at rest.
            </p>

            {/* Info Message */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {Object.entries(configData).map(([key, value]) => (
                <div key={key}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: '6px'
                  }}>
                    <label style={{
                      display: 'block',
                      color: '#FDFCFB',
                      fontSize: '14px',
                      fontWeight: '500'
                    }}>
                      {key}
                    </label>
                    <label style={{
                      display: 'flex',
                      alignItems: 'center',
                      cursor: 'pointer',
                      fontSize: '13px',
                      color: sensitiveFields.has(key) ? '#6bcf7f' : '#9b948f'
                    }}>
                      <input
                        type="checkbox"
                        checked={sensitiveFields.has(key)}
                        onChange={(e) => {
                          const newSet = new Set(sensitiveFields)
                          if (e.target.checked) {
                            newSet.add(key)
                          } else {
                            newSet.delete(key)
                          }
                          setSensitiveFields(newSet)
                        }}
                        style={{ marginRight: '6px' }}
                      />
                      {sensitiveFields.has(key) ? '🔒 Sensitive' : 'Mark as sensitive'}
                    </label>
                  </div>
                  <div style={{ position: 'relative' }}>
                    <input
                      type={sensitiveFields.has(key) && !visibleSensitiveFields.has(key) ? "password" : "text"}
                      value={configData[key] || ''}
                      placeholder={!configData[key] && sensitiveFields.has(key) ? "Enter credential (required)" : !configData[key] ? "Enter value" : ""}
                      onChange={(e) => {
                        setConfigData(prev => ({
                          ...prev,
                          [key]: e.target.value
                        }))
                      }}
                      style={{
                        width: '100%',
                        padding: sensitiveFields.has(key) ? '10px 45px 10px 12px' : '10px 12px',
                        backgroundColor: '#2a2a2a',
                        border: '1px solid #444',
                        borderRadius: '6px',
                        color: '#FDFCFB',
                        fontSize: '14px',
                        boxSizing: 'border-box'
                      }}
                    />
                    {sensitiveFields.has(key) && (
                      <button
                        type="button"
                        onClick={() => {
                          const newSet = new Set(visibleSensitiveFields)
                          if (newSet.has(key)) {
                            newSet.delete(key)
                          } else {
                            newSet.add(key)
                          }
                          setVisibleSensitiveFields(newSet)
                        }}
                        style={{
                          position: 'absolute',
                          right: '12px',
                          top: '50%',
                          transform: 'translateY(-50%)',
                          background: 'none',
                          border: 'none',
                          color: '#9b948f',
                          cursor: 'pointer',
                          padding: '4px',
                          fontSize: '16px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center'
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.color = '#FDFCFB'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.color = '#9b948f'
                        }}
                      >
                        {visibleSensitiveFields.has(key) ? '🙈' : '👀'}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Buttons */}
            <div style={{
              display: 'flex',
              gap: '12px',
              marginTop: '24px',
              justifyContent: 'flex-end'
            }}>
              {(() => {
                // Check if any fields are empty (null, undefined, or empty string)
                const hasEmptyFields = Object.values(configData).some(v =>
                  v === null || v === undefined || (typeof v === 'string' && v.trim() === '')
                )
                const isSubmitDisabled = configSubmitting || hasEmptyFields

                const button = (
                  <button
                    onClick={handleSubmitConfig}
                    disabled={isSubmitDisabled}
                    style={{
                      padding: '10px 20px',
                      backgroundColor: isSubmitDisabled ? '#2a2a2a' : '#306BEA',
                      color: isSubmitDisabled ? '#666' : '#FDFCFB',
                      border: isSubmitDisabled ? '1px solid #444' : 'none',
                      borderRadius: '6px',
                      cursor: isSubmitDisabled ? 'not-allowed' : 'pointer',
                      fontSize: '14px',
                      opacity: 1,
                      position: 'relative',
                      overflow: 'hidden',
                      width: '160px',
                      height: '40px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      transition: 'all 0.2s ease'
                    }}
                  >
                    {configSubmitting && (
                      <div style={{
                        position: 'absolute',
                        top: 0,
                        left: '-100%',
                        width: '100%',
                        height: '100%',
                        background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent)',
                        animation: 'shimmer 2s infinite'
                      }} />
                    )}
                    <span style={{
                      position: 'relative',
                      zIndex: 1,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px'
                    }}>
                      {configSubmitting && (
                        <div style={{
                          width: '12px',
                          height: '12px',
                          border: '2px solid #FDFCFB',
                          borderTop: '2px solid transparent',
                          borderRadius: '50%',
                          animation: 'spin 1s linear infinite'
                        }} />
                      )}
                      {configSubmitting ? 'Saving...' : configContext === 'debug' ? 'Save and Run' : configContext === 'generation' ? 'Save and Continue' : 'Save'}
                    </span>
                  </button>
                )

                // Only wrap with Tooltip if there's actually a tooltip to show
                return hasEmptyFields ? (
                  <Tooltip text="Please fill in all fields">
                    {button}
                  </Tooltip>
                ) : button
              })()}
            </div>
          </div>
        </div>
      )}

    </div>
  )
}

export default function App() {
  return (
    <>
      <style>
        {`
          @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
          }
          
          @keyframes fadeOut {
            from { opacity: 1; }
            to { opacity: 0; }
          }
          
          @keyframes slideInUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
          }
          
          @keyframes slideInDown {
            from { opacity: 0; transform: translateY(-30px); }
            to { opacity: 1; transform: translateY(0); }
          }
          
          @keyframes slideOutUp {
            from { opacity: 1; transform: translateY(0); }
            to { opacity: 0; transform: translateY(-30px); }
          }
          
          @keyframes slideOutDown {
            from { opacity: 1; transform: translateY(0); }
            to { opacity: 0; transform: translateY(30px); }
          }
          
          @keyframes scaleIn {
            from { opacity: 0; transform: scale(0.9); }
            to { opacity: 1; transform: scale(1); }
          }
          
          @keyframes quickFadeIn {
            from { opacity: 0.7; }
            to { opacity: 1; }
          }
          
          .page-fade-in {
            animation: fadeIn 0.4s ease-out;
          }
          
          .page-fade-out {
            animation: fadeOut 0.3s ease-in;
          }
          
          .slide-up-in {
            animation: slideInUp 0.4s ease-out;
          }
          
          .slide-down-in {
            animation: slideInDown 0.4s ease-out;
          }
          
          .slide-up-out {
            animation: slideOutUp 0.3s ease-in;
          }
          
          .slide-down-out {
            animation: slideOutDown 0.3s ease-in;
          }
          
          .scale-in {
            animation: scaleIn 0.3s ease-out;
          }
          
          .modal-backdrop {
            animation: fadeIn 0.2s ease-out;
          }
          
          .modal-content {
            animation: scaleIn 0.3s ease-out;
          }
          
          .content-transition {
            transition: all 0.3s ease;
          }
          
          .smooth-fade {
            transition: opacity 0.25s ease-in-out;
          }
          
          .page-container {
            animation: fadeIn 0.4s ease-out;
          }
          
          .tab-transition {
            transition: all 0.2s ease;
          }
          
          .tab-transition:hover {
            transform: translateY(-1px);
          }
          
          .content-fade-in {
            animation: quickFadeIn 0.15s ease-out;
          }
          
          .file-item-fade-in {
            animation: fadeIn 0.2s ease-out;
          }
          
          .file-item-fade-in:hover {
            transform: translateX(2px);
            transition: transform 0.2s ease;
          }
          
          .fade-out {
            animation: fadeOut 0.2s ease-in forwards;
          }
          
          .dynamic-element {
            transition: opacity 0.2s ease-in-out;
          }
          
          .files-loading {
            animation: filesLoadFade 0.4s ease-out;
          }
          
          @keyframes filesLoadFade {
            0% { opacity: 0.3; }
            50% { opacity: 0.1; }
            100% { opacity: 1; }
          }
        `}
      </style>
      <Routes>
      <Route
        path="/"
        element={<RootRedirect />}
      />
      <Route
        path="/home"
        element={
          <ProtectedRoute>
            <HomePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/create-connector"
        element={
          <ProtectedRoute>
            <CreateConnectorPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/ai-builder"
        element={
          <ProtectedRoute>
            <AIBuilderPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  )
}
