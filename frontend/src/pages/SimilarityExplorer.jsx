import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { 
  Dna, 
  Settings, 
  Map as MapIcon, 
  Activity, 
  ChevronRight,
  Filter,
  BarChart2,
  Table as TableIcon
} from 'lucide-react';
import WorkoutPCA from '../components/WorkoutPCA';
import WorkoutRadar from '../components/WorkoutRadar';
import { getPcaData } from '../utils/api';

const SimilarityExplorer = () => {
  const navigate = useNavigate();
  const [activeType, setActiveType] = useState('Run');
  const [selectedId, setSelectedId] = useState(null);
  const [activeTab, setActiveTab] = useState('scatter'); // 'scatter', 'comparison', 'distribution'
  const [comparisonData, setComparisonData] = useState(null);
  const pcaQuery = useQuery({
    queryKey: ['pca', activeType],
    queryFn: () => getPcaData(activeType),
  });
  const loading = pcaQuery.isLoading;
  const pcaData = pcaQuery.data;

  const handleSelectActivity = async (id) => {
    setSelectedId(id);
    
    // Fetch similar matches for highlighting or comparison
    try {
      const resp = await fetch(`/api/activities/${id}/similar?top_n=5`);
      const data = await resp.json();
      
      // If we're in comparison tab, fetch full comparison data
      if (activeTab === 'comparison') {
        const ids = [id, ...data.similar.map(s => s.activity.id)];
        const compResp = await fetch('/api/activities/compare', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ activity_ids: ids })
        });
        const compData = await compResp.json();
        setComparisonData(compData);
      }
    } catch (err) {
      console.error("Error selecting activity:", err);
    }
  };

  const selectedActivity = pcaData?.activities.find(a => a.id === selectedId);

  return (
    <div className="similarity-explorer">
      {/* Header */}
      <div className="explorer-header">
        <div>
          <div className="header-badge">
            <div className="header-badge-icon">
              <Dna size={20} />
            </div>
            <span className="header-badge-text">Similarity Engine</span>
          </div>
          <h1 className="explorer-title">Archetype Explorer</h1>
          <p className="explorer-subtitle">Visually discover patterns and clusters across your workouts using PCA.</p>
        </div>

        <div className="type-switcher">
          {['Run', 'Ride', 'Hike'].map(type => (
            <button
              key={type}
              onClick={() => setActiveType(type)}
              className={`type-btn ${activeType === type ? 'active' : ''}`}
            >
              {type}s
            </button>
          ))}
        </div>
      </div>

      <div className="explorer-content">
        {/* Sidebar / Info */}
        <div className="explorer-sidebar">
          <div className="sidebar-card">
            <h3 className="sidebar-title">
              <Filter size={14} /> View mode
            </h3>
            <nav className="view-mode-nav">
              <button 
                onClick={() => setActiveTab('scatter')}
                className={`mode-btn ${activeTab === 'scatter' ? 'active' : ''}`}
              >
                <div className="mode-btn-icon">
                  <Activity size={16} />
                </div>
                <span className="mode-btn-text">PCA Scatter</span>
              </button>
              <button 
                onClick={() => setActiveTab('comparison')}
                className={`mode-btn ${activeTab === 'comparison' ? 'active' : ''}`}
              >
                <div className="mode-btn-icon">
                  <BarChart2 size={16} />
                </div>
                <span className="mode-btn-text">Radar Profile</span>
              </button>
              <button 
                disabled
                className="mode-btn disabled"
                style={{ opacity: 0.3, cursor: 'not-allowed' }}
              >
                <div className="mode-btn-icon">
                  <TableIcon size={16} />
                </div>
                <span className="mode-btn-text">Distributions</span>
              </button>
            </nav>
          </div>

          {selectedActivity && (
            <div className="sidebar-card selected-activity-card">
              <h3 className="sidebar-title" style={{ color: 'var(--text-accent)' }}>Selected Activity</h3>
              <h2 className="selected-activity-name">{selectedActivity.name}</h2>
              
              <div className="activity-detail-mini">
                <div className="mini-row">
                  <span className="mini-label">Distance</span>
                  <span className="mini-value">{selectedActivity.distance_miles.toFixed(2)} mi</span>
                </div>
                <div className="mini-row">
                  <span className="mini-label">Date</span>
                  <span className="mini-value">{selectedActivity.date}</span>
                </div>
                <div className="mini-row">
                  <span className="mini-label">Cluster</span>
                  <span className="mini-value">Archetype {selectedActivity.cluster}</span>
                </div>
              </div>

              <button 
                onClick={() => navigate(`/activity/${selectedId}`)}
                className="view-full-btn"
              >
                View Details <ChevronRight size={16} />
              </button>
            </div>
          )}

          <div className="sidebar-card" style={{ background: 'transparent', borderStyle: 'dashed' }}>
            <h3 className="sidebar-title">
              <Settings size={12} /> Data Info
            </h3>
            <p style={{ fontSize: '10px', color: 'var(--text-muted)', lineHeight: '1.5' }}>
              PCA components are derived from distance, pace, elevation, heartrate, and duration.
              PC1 usually represents exercise 'Volume' while PC2 represents 'Intensity'.
            </p>
          </div>
        </div>

        {/* Main Viz Area */}
        <div className="explorer-main">
          {loading ? (
            <div className="loading-state glass-card" style={{ height: '600px' }}>
              <div className="loading-spinner" />
              <span>Computing PCA space...</span>
            </div>
          ) : pcaData && activeTab === 'scatter' ? (
            <WorkoutPCA 
              data={pcaData.activities} 
              loadings={pcaData.loadings}
              onSelectActivity={handleSelectActivity}
              selectedId={selectedId}
            />
          ) : activeTab === 'comparison' && comparisonData ? (
            <div className="radar-comparison-view">
              <h3 className="section-title" style={{ marginBottom: 'var(--space-xl)' }}>Group Profile: Selected vs Similar Cluster</h3>
              <div style={{ width: '100%', maxWidth: '600px', height: '400px' }}>
                <WorkoutRadar activities={comparisonData.comparisons.map(c => c.activity)} />
              </div>
              <div className="radar-comp-grid">
                {comparisonData.comparisons.map((c, i) => (
                  <div key={c.activity.id} className="comp-preview-card">
                    <span className="comp-preview-label">ACTIVITY {i+1}</span>
                    <span className="comp-preview-name">{c.activity.name}</span>
                    <span className="comp-preview-date">{c.activity.date}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="empty-state glass-card" style={{ height: '600px' }}>
              <BarChart2 size={48} style={{ opacity: 0.1, marginBottom: 'var(--space-md)' }} />
              <h3 className="section-title">Select an activity to compare</h3>
              <p className="section-subtitle">Pick a dot on the PCA scatter plot first to generate a profile comparison.</p>
              <button 
                onClick={() => setActiveTab('scatter')}
                className="filter-chip active"
                style={{ marginTop: 'var(--space-lg)' }}
              >
                Go to Scatter Plot
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SimilarityExplorer;
