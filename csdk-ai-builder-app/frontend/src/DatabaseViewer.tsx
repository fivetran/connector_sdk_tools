import { useState, useEffect, useRef, useCallback } from 'react'

// API Base URL configuration
// When running locally: use direct backend connection
// When running via nginx: use /api prefix (nginx proxies to backend)
const host = window.location.hostname
const API_BASE = (host === 'localhost' || host === '127.0.0.1')
  ? 'http://localhost:8001'
  : '/api'

interface Table {
  schema: string
  table: string
  full_name: string
}

interface Column {
  column_name: string
  column_type: string
  null: string
  key: string
  default: string
  extra: string
}

interface TableStructure {
  table_name: string
  total_rows: number
  total_columns: number
  columns: Column[]
}

interface DatabaseViewerProps {
  username: string
  projectName: string
  onClose?: () => void // Optional for inline usage
}

export default function DatabaseViewer({ username, projectName, onClose }: DatabaseViewerProps) {
  const isModal = !!onClose // If onClose is provided, it's used as a modal
  const [activeTab, setActiveTab] = useState<'preview' | 'structure' | 'query'>('preview')
  const [tables, setTables] = useState<Table[]>([])
  const [selectedTable, setSelectedTable] = useState<string>('')
  const [tableData, setTableData] = useState<any[]>([])
  const [tableStructure, setTableStructure] = useState<TableStructure | null>(null)
  const [customQuery, setCustomQuery] = useState<string>('')
  const [queryResult, setQueryResult] = useState<any[]>([])
  const [queryColumns, setQueryColumns] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>('')
  const [tableLoading, setTableLoading] = useState(false)
  const [queryLoading, setQueryLoading] = useState(false)
  const [queryError, setQueryError] = useState<string>('')
  const [queryExecuted, setQueryExecuted] = useState(false)
  
  // Ref for auto-resizing SQL textarea
  const sqlTextareaRef = useRef<HTMLTextAreaElement>(null)

  // AbortController ref for cancelling ongoing requests on unmount/refresh
  const abortControllerRef = useRef<AbortController | null>(null)

  // Cleanup function to cancel ongoing requests
  const cancelOngoingRequests = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
  }, [])

  // Handle page unload (refresh, close, navigate away)
  useEffect(() => {
    const handleBeforeUnload = () => {
      cancelOngoingRequests()
    }

    window.addEventListener('beforeunload', handleBeforeUnload)

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
      // Also cancel on component unmount
      cancelOngoingRequests()
    }
  }, [cancelOngoingRequests])
  
  // Auto-resize SQL textarea based on content
  const autoResizeSqlTextarea = () => {
    const textarea = sqlTextareaRef.current
    if (textarea) {
      // Reset height to auto to get the actual content height
      textarea.style.height = 'auto'
      // Set height to scrollHeight, but maintain minimum height of 100px
      const minHeight = 100 // Matches current height
      textarea.style.height = Math.max(textarea.scrollHeight, minHeight) + 'px'
    }
  }

  useEffect(() => {
    checkDatabase()
  }, [username, projectName])
  
  // Auto-resize SQL textarea when customQuery changes from other sources
  useEffect(() => {
    autoResizeSqlTextarea()
  }, [customQuery])

  // Auto-execute query when switching to custom query tab
  useEffect(() => {
    if (activeTab === 'query' && customQuery.trim() && !queryLoading) {
      // Small delay to ensure tab switch is complete
      setTimeout(() => {
        executeQueryWithText(customQuery)
      }, 100)
    }
  }, [activeTab])

  const checkDatabase = async () => {
    setLoading(true)
    setError('')

    // Cancel any previous request and create new controller
    cancelOngoingRequests()
    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch(`${API_BASE}/database/check`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          username,
          project_name: projectName
        }),
        signal: abortControllerRef.current.signal
      })

      if (!response.ok) {
        const errorText = await response.text()
        console.error('HTTP error checking database:', response.status, errorText)
        setError(`HTTP ${response.status}: ${errorText || response.statusText}`)
        return
      }

      const data = await response.json()

      if (data.success) {
        setTables(data.tables || [])
        if (data.tables && data.tables.length > 0) {
          setSelectedTable(data.tables[0].full_name)
          loadTableData(data.tables[0].full_name)
        }
      } else {
        console.error('Backend error checking database:', data.message)
        setError(data.message || 'Failed to load database')
      }
    } catch (err: any) {
      // Ignore abort errors (expected on page refresh/unmount)
      if (err?.name === 'AbortError') {
        return
      }
      console.error('Error checking database:', err)
      setError(`Failed to connect to database: ${err?.message || err}`)
    } finally {
      setLoading(false)
    }
  }

  const loadTableData = async (tableName: string) => {
    if (!tableName) return

    setTableLoading(true)

    // Cancel any previous request and create new controller
    cancelOngoingRequests()
    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch(`${API_BASE}/database/table-data`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          username,
          project_name: projectName,
          table_name: tableName
        }),
        signal: abortControllerRef.current.signal
      })

      if (!response.ok) {
        const errorText = await response.text()
        console.error('HTTP error loading table data:', response.status, errorText)
        setError(`HTTP ${response.status}: ${errorText || response.statusText}`)
        return
      }

      const data = await response.json()

      if (data.success) {
        setTableData(data.preview || [])
        setTableStructure(data.structure)
        const defaultQuery = data.default_query || ''
        setCustomQuery(defaultQuery)

        // Auto-execute query if we're on the custom query tab and have a default query
        if (activeTab === 'query' && defaultQuery.trim()) {
          // Use setTimeout to ensure state update completes first
          setTimeout(() => {
            executeQueryWithText(defaultQuery)
          }, 0)
        }
      } else {
        console.error('Backend error loading table data:', data.message)
        setError(data.message || 'Failed to load table data')
      }
    } catch (err: any) {
      // Ignore abort errors (expected on page refresh/unmount)
      if (err?.name === 'AbortError') {
        return
      }
      console.error('Error loading table data:', err)
      setError(`Failed to load table data: ${err?.message || err}`)
    } finally {
      setTableLoading(false)
    }
  }

  const executeQueryWithText = async (queryText: string) => {
    if (!queryText.trim()) return

    setQueryLoading(true)
    setQueryError('')
    setQueryExecuted(true)

    // Cancel any previous request and create new controller
    cancelOngoingRequests()
    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch(`${API_BASE}/database/custom-query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          username,
          project_name: projectName,
          query: queryText
        }),
        signal: abortControllerRef.current.signal
      })

      const data = await response.json()
      
      if (data.success) {
        setQueryResult(data.result || [])
        setQueryColumns(data.column_names || [])
        setQueryError('')
      } else {
        setQueryError(data.message || 'Query failed')
        setQueryResult([])
        setQueryColumns([])
      }
    } catch (err: any) {
      // Ignore abort errors (expected on page refresh/unmount)
      if (err?.name === 'AbortError') {
        return
      }
      console.error('Error executing query:', err)
      setQueryError('Failed to execute query')
      setQueryResult([])
      setQueryColumns([])
    } finally {
      setQueryLoading(false)
    }
  }

  const executeQuery = async () => {
    if (!customQuery.trim()) return

    setQueryLoading(true)
    setQueryError('')
    setQueryExecuted(true)

    // Cancel any previous request and create new controller
    cancelOngoingRequests()
    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch(`${API_BASE}/database/custom-query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          username,
          project_name: projectName,
          query: customQuery
        }),
        signal: abortControllerRef.current.signal
      })

      const data = await response.json()
      
      if (data.success) {
        setQueryResult(data.result || [])
        setQueryColumns(data.column_names || [])
        setQueryError('')
      } else {
        setQueryError(data.message || 'Query failed')
        setQueryResult([])
        setQueryColumns([])
      }
    } catch (err: any) {
      // Ignore abort errors (expected on page refresh/unmount)
      if (err?.name === 'AbortError') {
        return
      }
      console.error('Error executing query:', err)
      setQueryError('Failed to execute query')
      setQueryResult([])
      setQueryColumns([])
    } finally {
      setQueryLoading(false)
    }
  }

  const handleTableChange = (tableName: string) => {
    setSelectedTable(tableName)
    // Clear existing data before loading new table
    setTableData([])
    setTableStructure(null)
    setQueryExecuted(false) // Reset query execution state
    loadTableData(tableName)
  }

  const renderTable = (data: any[], columns?: string[], maxHeight?: string) => {
    if (tableLoading) {
      return (
        <div style={{ 
          padding: '40px', 
          textAlign: 'center', 
          color: '#FDFCFB'
        }}>
          <div style={{ marginBottom: '8px' }}>Loading table data...</div>
          <div style={{ 
            width: '20px', 
            height: '20px', 
            border: '2px solid #333',
            borderTop: '2px solid #306BEA',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
            margin: '0 auto'
          }}></div>
        </div>
      )
    }

    if (!data || data.length === 0) {
      return (
        <div style={{ 
          padding: '40px', 
          textAlign: 'center', 
          color: '#9b948f',
          fontStyle: 'italic'
        }}>
          No data available
        </div>
      )
    }

    const displayColumns = columns || Object.keys(data[0] || {})

    return (
      <div style={{ 
        overflow: 'auto', 
        ...(maxHeight && { maxHeight }), 
        paddingBottom: '20px' 
      }}>
        <table style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: '12px',
          backgroundColor: '#2a2a2a'
        }}>
          <thead>
            <tr style={{ backgroundColor: '#1a1a1a', position: 'sticky', top: 0 }}>
              {displayColumns.map((col, index) => (
                <th key={index} style={{
                  padding: '8px 12px',
                  textAlign: 'left',
                  borderBottom: '1px solid #444',
                  color: '#FDFCFB',
                  fontWeight: '600',
                  fontSize: '11px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px'
                }}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, rowIndex) => (
              <tr key={rowIndex} style={{
                borderBottom: '1px solid #333'
              }}>
                {displayColumns.map((col, colIndex) => (
                  <td key={colIndex} style={{
                    padding: '8px 12px',
                    color: '#FDFCFB',
                    fontSize: '11px',
                    fontFamily: 'monospace',
                    maxWidth: '200px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>
                    {row[col] !== null && row[col] !== undefined ? String(row[col]) : '(null)'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (loading) {
    const loadingContent = (
      <div style={{
        background: '#1B1818',
        borderRadius: isModal ? '12px' : '0',
        padding: '40px',
        color: '#FDFCFB',
        border: isModal ? '1px solid #333' : 'none',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%'
      }}>
        Loading database...
      </div>
    )

    if (isModal) {
      return (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          {loadingContent}
        </div>
      )
    }

    return loadingContent
  }

  if (error) {
    const errorContent = (
      <div style={{
        background: '#1B1818',
        borderRadius: isModal ? '12px' : '0',
        padding: '40px',
        color: '#FDFCFB',
        border: isModal ? '1px solid #333' : 'none',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%'
      }}>
        <div style={{ marginBottom: '20px', color: '#ff6b6b' }}>
          ❌ {error}
        </div>
        {isModal && onClose && (
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px',
              background: '#306BEA',
              color: '#FDFCFB',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '14px'
            }}
          >
            Close
          </button>
        )}
      </div>
    )

    if (isModal) {
      return (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          {errorContent}
        </div>
      )
    }

    return errorContent
  }

  const mainContent = (
    <>
      <style>
        {`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
          
          @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
          }
          
          @keyframes fadeOut {
            from { opacity: 1; }
            to { opacity: 0; }
          }
          
          @keyframes slideIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
          }
          
          @keyframes slideOut {
            from { opacity: 1; transform: translateY(0); }
            to { opacity: 0; transform: translateY(-20px); }
          }
          
          .fade-in {
            animation: fadeIn 0.3s ease-in-out;
          }
          
          .fade-out {
            animation: fadeOut 0.3s ease-in-out;
          }
          
          .slide-in {
            animation: slideIn 0.4s ease-out;
          }
          
          .slide-out {
            animation: slideOut 0.3s ease-in;
          }
          
          .tab-transition {
            transition: all 0.3s ease;
          }
          
          .content-fade {
            transition: opacity 0.25s ease-in-out;
          }
          
          .modal-backdrop {
            animation: fadeIn 0.2s ease-out;
          }
          
          .modal-content {
            animation: slideIn 0.3s ease-out;
          }
        `}
      </style>
      <div style={{
        background: '#1B1818',
        borderRadius: isModal ? '12px' : '0',
        padding: '0',
        width: isModal ? '90vw' : '100%',
        height: isModal ? '80vh' : '100%',
        border: isModal ? '1px solid #333' : 'none',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden'
      }}>
        {/* Header */}
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          padding: '20px 24px',
          borderBottom: '1px solid #333'
        }}>
          <h2 style={{ 
            margin: '0', 
            color: '#FDFCFB', 
            fontSize: '18px',
            fontWeight: '600'
          }}>
            Database Viewer - {projectName}
          </h2>
          {isModal && onClose && (
            <button
              onClick={onClose}
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
            >
              ×
            </button>
          )}
        </div>

        {/* Table Selector */}
        <div style={{ padding: '16px 24px', borderBottom: '1px solid #333' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <label style={{ color: '#FDFCFB', fontSize: '14px', fontWeight: '500' }}>
              Table:
            </label>
            <select
              value={selectedTable}
              onChange={(e) => handleTableChange(e.target.value)}
              style={{
                padding: '6px 12px',
                backgroundColor: '#2a2a2a',
                border: '1px solid #444',
                borderRadius: '6px',
                color: '#FDFCFB',
                fontSize: '14px',
                minWidth: '200px'
              }}
            >
              {tables.map((table) => (
                <option key={table.full_name} value={table.full_name}>
                  {table.full_name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ 
          display: 'flex', 
          borderBottom: '1px solid #333',
          backgroundColor: '#1a1a1a'
        }}>
          {[
            { key: 'preview', label: 'Data Preview' },
            { key: 'structure', label: 'Table Structure' },
            { key: 'query', label: 'Custom Query' }
          ].map((tab) => (
            <button
              key={tab.key}
              className="tab-transition"
              onClick={() => setActiveTab(tab.key as any)}
              style={{
                padding: '12px 24px',
                background: activeTab === tab.key ? '#306BEA' : 'transparent',
                color: activeTab === tab.key ? '#FDFCFB' : '#9b948f',
                border: 'none',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: '500',
                transition: 'all 0.2s ease'
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {/* Data Preview Tab */}
          <div className={activeTab === 'preview' ? 'content-fade-in' : ''} style={{ display: activeTab === 'preview' ? 'block' : 'none', padding: '20px', flex: 1, overflow: 'auto' }}>
              <h3 style={{ margin: '0 0 16px 0', color: '#FDFCFB', fontSize: '16px' }}>
                Data Preview - {selectedTable}
              </h3>
              {renderTable(tableData, undefined, '400px')}
          </div>

          {/* Table Structure Tab */}
          <div className={activeTab === 'structure' ? 'content-fade-in' : ''} style={{ display: activeTab === 'structure' && tableStructure ? 'block' : 'none', padding: '20px', flex: 1, overflow: 'auto' }}>
              {tableStructure && (
                <>
                  <h3 style={{ margin: '0 0 16px 0', color: '#FDFCFB', fontSize: '16px' }}>
                    Table Structure - {tableStructure.table_name}
                  </h3>
                  <div style={{ marginBottom: '20px' }}>
                    <div style={{ color: '#9b948f', fontSize: '14px', marginBottom: '8px' }}>
                      Total Rows: <span style={{ color: '#FDFCFB' }}>{tableStructure.total_rows.toLocaleString()}</span>
                    </div>
                    <div style={{ color: '#9b948f', fontSize: '14px' }}>
                      Total Columns: <span style={{ color: '#FDFCFB' }}>{tableStructure.total_columns}</span>
                    </div>
                  </div>
                  {renderTable(tableStructure.columns, undefined, '400px')}
                </>
              )}
          </div>

          {/* Custom Query Tab */}
          <div className={activeTab === 'query' ? 'content-fade-in' : ''} style={{ display: activeTab === 'query' ? 'flex' : 'none', padding: '20px', flex: 1, flexDirection: 'column', gap: '16px', overflow: 'auto' }}>
              <h3 style={{ margin: '0', color: '#FDFCFB', fontSize: '16px' }}>
                Custom Query
              </h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <textarea
                  ref={sqlTextareaRef}
                  value={customQuery}
                  onChange={(e) => {
                    setCustomQuery(e.target.value)
                    // Auto-resize textarea after content change
                    setTimeout(autoResizeSqlTextarea, 0)
                  }}
                  placeholder="Enter your SQL query here..."
                  style={{
                    width: '100%',
                    minHeight: '100px',
                    padding: '12px',
                    backgroundColor: '#2a2a2a',
                    border: '1px solid #444',
                    borderRadius: '6px',
                    color: '#FDFCFB',
                    fontSize: '12px',
                    fontFamily: 'monospace',
                    resize: 'none',
                    overflow: 'hidden',
                    outline: 'none'
                  }}
                />
                
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                  <button
                    onClick={executeQuery}
                    disabled={queryLoading || !customQuery.trim()}
                    style={{
                      padding: '8px 16px',
                      background: queryLoading || !customQuery.trim() ? '#666' : '#306BEA',
                      color: '#FDFCFB',
                      border: 'none',
                      borderRadius: '6px',
                      cursor: queryLoading || !customQuery.trim() ? 'not-allowed' : 'pointer',
                      fontSize: '14px'
                    }}
                  >
                    {queryLoading ? 'Executing...' : 'Execute Query'}
                  </button>
                  
                  {queryError && (
                    <div style={{ color: '#ff6b6b', fontSize: '14px' }}>
                      {queryError}
                    </div>
                  )}
                </div>
              </div>

              {queryExecuted && (
                <div style={{ flex: 1, overflow: 'auto' }}>
                  <h4 style={{ margin: '0 0 12px 0', color: '#FDFCFB', fontSize: '14px' }}>
                    Query Result ({queryResult.length} rows)
                  </h4>
                  {renderTable(queryResult, queryColumns)}
                </div>
              )}
          </div>
        </div>
      </div>
    </>
  )

  if (isModal) {
    return (
      <div style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000
      }}>
        {mainContent}
      </div>
    )
  }

  return mainContent
}
