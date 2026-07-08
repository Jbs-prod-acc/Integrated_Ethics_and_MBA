import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import base64
import random
import numpy as np
from datetime import datetime, timedelta
import pytz

# Utility function to save plot as base64 string
def fig_to_base64(fig=None):
    buffer = io.BytesIO()
    if fig:
        fig.savefig(buffer, format="png", bbox_inches="tight", dpi=150, facecolor='white')
        plt.close(fig)
    else:
        plt.savefig(buffer, format="png", bbox_inches="tight", dpi=150, facecolor='white')
        plt.close()
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_base64}"

# Utility function to generate random color palette
def random_palette(n):
    """Generate a random color palette with n colors"""
    colors = []
    for _ in range(n):
        colors.append((random.random(), random.random(), random.random()))
    return colors

# Professional color schemes
GOOGLE_ANALYTICS_COLORS = ['#4285F4', '#34A853', '#FBBC05', '#EA4335', '#9AA0A6', '#FF6D01', '#46BDC6']
UJ_BRAND_COLORS_LIST = ['#022169', '#EF820D', '#1E90FF', '#32CD32', '#FFD700', '#FF6347', '#9370DB']

# Dictionary version for named colors
UJ_BRAND_COLORS = {
    'primary': '#022169',    # Deep blue
    'secondary': '#EF820D',  # Orange
    'success': '#32CD32',    # Green
    'info': '#1E90FF',       # Light blue
    'warning': '#FFD700',    # Gold
    'danger': '#FF6347',     # Red
    'purple': '#9370DB'      # Purple
}

# Set professional styling
plt.style.use('default')
sns.set_palette(UJ_BRAND_COLORS_LIST)

def get_professional_palette(n):
    """Get professional color palette"""
    colors = (UJ_BRAND_COLORS_LIST + GOOGLE_ANALYTICS_COLORS)[:n]
    if len(colors) < n:
        # Generate additional colors if needed
        colors.extend([f"#{random.randint(0, 0xFFFFFF):06x}" for _ in range(n - len(colors))])
    return colors

def setup_professional_plot(figsize=(16,10)):
    """Setup professional plot styling"""
    fig, ax = plt.subplots(figsize=figsize)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, alpha=0.3)
    ax.set_facecolor('#fafafa')
    return fig, ax

def create_plotly_chart(fig):
    """Convert Plotly figure to HTML div"""
    return fig.to_html(include_plotlyjs='cdn', div_id=f"chart_{random.randint(1000, 9999)}", 
                      config={'displayModeBar': True, 'displaylogo': False})

###
### PLOT FORM A
###

# Enhanced KPI Calculation Function
def calculate_kpis_a(df):
    """Calculate key performance indicators for Form A"""
    if df.empty:
        return {}
    
    total_applications = len(df.drop_duplicates(subset=['id'])) if 'id' in df.columns else len(df)
    
    # Time-based metrics
    if 'submitted_at' in df.columns:
        df['submitted_at'] = pd.to_datetime(df['submitted_at'], errors='coerce')
        
        # Remove timezone info to avoid comparison issues
        # Convert to naive datetime for comparison
        if df['submitted_at'].dt.tz is not None:
            df['submitted_at'] = df['submitted_at'].dt.tz_localize(None)
        
        # Use timezone-naive datetime
        now = datetime.now()
        last_30_days = df[df['submitted_at'] >= (now - timedelta(days=30))]
        this_month = len(last_30_days)
        
        prev_30_days = df[(df['submitted_at'] >= (now - timedelta(days=60))) & 
                         (df['submitted_at'] < (now - timedelta(days=30)))]
        prev_month = len(prev_30_days)
        growth_rate = ((this_month - prev_month) / prev_month * 100) if prev_month > 0 else 0
    else:
        this_month = total_applications
        growth_rate = 0

    # Certificate metrics
    certificates_issued = df['certificate_issued'].notna().sum() if 'certificate_issued' in df.columns else 0
    certificates_received = df['certificate_received'].sum() if 'certificate_received' in df.columns else 0
    
    # Risk distribution
    high_risk = len(df[df['risk_rating'].str.contains('High|high', na=False)]) if 'risk_rating' in df.columns else 0
    
    # Review completion rate
    review_completed = 0
    if 'review_recommendation' in df.columns and 'review_recommendation1' in df.columns:
        review_completed = len(df[df['review_recommendation'].notna() & df['review_recommendation1'].notna()])
    
    completion_rate = (review_completed / total_applications * 100) if total_applications > 0 else 0
    
    return {
        'total_applications': total_applications,
        'this_month': this_month,
        'growth_rate': round(growth_rate, 1),
        'certificates_issued': certificates_issued,
        'certificates_received': certificates_received,
        'completion_rate': round(completion_rate, 1),
        'high_risk_count': high_risk
    }

# Enhanced Sunburst Chart for Application Flow
def create_sunburst_chart_a(df):
    """Create interactive sunburst chart for Form A application flow"""
    if df.empty:
        return "<div class='alert alert-info'>No data available for sunburst visualization</div>"
    
    # Prepare hierarchical data
    sunburst_data = []
    
    # Level 1: Risk Rating
    for risk in df['risk_rating'].dropna().unique():
        risk_df = df[df['risk_rating'] == risk]
        
        # Level 2: Review Status
        for status in ['Pending Review', 'Under Review', 'Approved', 'Needs Revision']:
            if 'review_recommendation' in df.columns:
                if status == 'Approved':
                    status_df = risk_df[risk_df['review_recommendation'].str.contains('Approved', na=False)]
                elif status == 'Needs Revision':
                    status_df = risk_df[risk_df['review_recommendation'].str.contains('Revision|Resubmission', na=False)]
                elif status == 'Under Review':
                    status_df = risk_df[risk_df['review_recommendation'].notna() & 
                                      ~risk_df['review_recommendation'].str.contains('Approved|Revision|Resubmission', na=False)]
                else:  # Pending
                    status_df = risk_df[risk_df['review_recommendation'].isna()]
            else:
                status_df = risk_df if status == 'Pending Review' else pd.DataFrame()
            
            if len(status_df) > 0:
                # Level 3: Certificate Status
                cert_issued = len(status_df[status_df['certificate_issued'].notna()]) if 'certificate_issued' in status_df.columns else 0
                cert_pending = len(status_df) - cert_issued
                
                if cert_issued > 0:
                    sunburst_data.append({
                        'ids': f"{risk}-{status}-Certified",
                        'labels': 'Certificate Issued',
                        'parents': f"{risk}-{status}",
                        'values': cert_issued
                    })
                
                if cert_pending > 0:
                    sunburst_data.append({
                        'ids': f"{risk}-{status}-Pending",
                        'labels': 'Certificate Pending',
                        'parents': f"{risk}-{status}",
                        'values': cert_pending
                    })
                
                sunburst_data.append({
                    'ids': f"{risk}-{status}",
                    'labels': status,
                    'parents': risk,
                    'values': len(status_df)
                })
        
        sunburst_data.append({
            'ids': risk,
            'labels': risk,
            'parents': "",
            'values': len(risk_df)
        })

    if not sunburst_data:
        return "<div class='alert alert-warning'>Insufficient data for sunburst visualization</div>"

    fig = go.Figure(go.Sunburst(
        ids=[item['ids'] for item in sunburst_data],
        labels=[item['labels'] for item in sunburst_data],
        parents=[item['parents'] for item in sunburst_data],
        values=[item['values'] for item in sunburst_data],
        branchvalues="total",
        hovertemplate='<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percentParent}<extra></extra>',
        maxdepth=3,
        marker=dict(colors=UJ_BRAND_COLORS_LIST)
    ))

    fig.update_layout(
        title={
            'text': "Form A Application Flow Analysis",
            'x': 0.5,
            'font': {'size': 18, 'family': 'Arial, sans-serif'}
        },
        font_size=12,
        height=500,
        margin=dict(t=60, l=20, r=20, b=20),
        paper_bgcolor='white',
        plot_bgcolor='white'
    )

    return create_plotly_chart(fig)

# 1️⃣ Enhanced Risk Rating Distribution
def plot_risk_rating_distribution_a(df):
    """Enhanced professional risk rating distribution"""
    if df.empty:
        return fig_to_base64()
    
    fig, ax = setup_professional_plot(figsize=(16,10))
    
    # Count and sort data
    risk_counts = df['risk_rating'].value_counts()
    colors = get_professional_palette(len(risk_counts))
    
    # Create bar plot
    bars = ax.bar(risk_counts.index, risk_counts.values, color=colors, alpha=0.8, edgecolor='white', linewidth=2)
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                f'{int(height)}', ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    # Styling
    ax.set_title('Applications by Risk Rating', fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('Risk Rating', fontsize=12, fontweight='bold')
    ax.set_ylabel('Number of Applications', fontsize=12, fontweight='bold')
    
    # Add percentage labels
    total = risk_counts.sum()
    for i, (category, count) in enumerate(risk_counts.items()):
        percentage = (count / total) * 100
        ax.text(i, count/2, f'{percentage:.1f}%', ha='center', va='center', 
                fontweight='bold', fontsize=10, color='white')
    
    plt.tight_layout()
    return fig_to_base64(fig)

# 2️⃣ Review Recommendations Breakdown
def plot_review_recommendations_a(df):
    plt.figure(figsize=(12,8))
    categories = df['review_recommendation'].nunique()
    sns.countplot(x="review_recommendation", data=df, palette=random_palette(categories), width=0.6)
    plt.title("Review Recommendations")
    plt.xticks(rotation=45)
    return fig_to_base64()

# 3️⃣ Supervisor Recommendations Breakdown
def plot_supervisor_recommendations_a(df):
    plt.figure(figsize=(12,8))
    categories = df['supervisor_recommendation'].nunique()
    sns.countplot(x="supervisor_recommendation", data=df, palette=random_palette(categories), width=0.6)
    plt.title("Supervisor Recommendations")
    plt.xticks(rotation=45)
    return fig_to_base64()

# 4️⃣ Number of Applications per REC Member
def plot_rec_member_distribution_a(df):
    plt.figure(figsize=(12,8))
    categories = df['rec_full_name'].nunique()
    sns.countplot(y="rec_full_name", data=df, palette=random_palette(categories), width=0.6)
    plt.title("Applications Reviewed by Each REC Member")
    return fig_to_base64()

# 5️⃣ Certificate Issued vs Not Issued
def plot_certificate_status_a(df):
    plt.figure(figsize=(12,8))
    categories = df['certificate_issued'].nunique()
    sns.countplot(x="certificate_issued", data=df, palette=random_palette(categories), width=0.6)
    plt.title("Certificate Issuance Status")
    return fig_to_base64()

# 6️⃣ Applications Submitted Over Time
def plot_submissions_over_time_a(df):
    """Plot submissions over time with proper error handling"""
    if df.empty or 'submitted_at' not in df.columns:
        return None
    
    df['submitted_at'] = pd.to_datetime(df['submitted_at'], errors='coerce')
    
    # Remove rows with invalid dates
    df_valid = df[df['submitted_at'].notna()]
    
    if df_valid.empty:
        return None
    
    # Group by date and count submissions
    submissions_by_date = df_valid.groupby(df_valid['submitted_at'].dt.date).size()
    
    if submissions_by_date.empty:
        return None
    
    plt.figure(figsize=(14,8))
    submissions_by_date.plot(kind='bar', color=random_palette(len(submissions_by_date)), width=0.6)
    plt.title("Submissions Over Time")
    plt.xlabel("Date")
    plt.ylabel("Number of Submissions")
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    return fig_to_base64()

# 7️⃣ Review Recommendation by Risk Rating (stacked bar)
def plot_review_by_risk_rating_a(df):
    if df.empty or 'risk_rating' not in df.columns:
        return None
    
    # Try both review_recommendation columns (primary and secondary)
    has_primary = 'review_recommendation' in df.columns
    has_secondary = 'review_recommendation1' in df.columns
    
    if not has_primary and not has_secondary:
        return None
    
    # Use whichever review recommendation column has more data
    if has_primary and has_secondary:
        primary_count = df['review_recommendation'].notna().sum()
        secondary_count = df['review_recommendation1'].notna().sum()
        review_col = 'review_recommendation' if primary_count >= secondary_count else 'review_recommendation1'
    elif has_primary:
        review_col = 'review_recommendation'
    else:
        review_col = 'review_recommendation1'
    
    # Remove rows with null values
    df_valid = df[df['risk_rating'].notna() & df[review_col].notna()]
    
    if df_valid.empty:
        return None
    
    plt.figure(figsize=(14,8))
    review_risk = pd.crosstab(df_valid['risk_rating'], df_valid[review_col])
    
    if review_risk.empty:
        return None
    
    colors = random_palette(review_risk.shape[1])
    review_risk.plot(kind='bar', stacked=True, ax=plt.gca(), color=colors, width=0.6)
    plt.title("Review Recommendation by Risk Rating")
    plt.xlabel("Risk Rating")
    plt.ylabel("Count")
    plt.xticks(rotation=45, ha='right')
    plt.legend(title="Review Recommendation", bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    return fig_to_base64()

# 8️⃣ Top Applicants by Submission Count
def plot_top_applicants_a(df):
    if df.empty or 'applicant_name' not in df.columns:
        return None
    
    df_valid = df[df['applicant_name'].notna()]
    
    if df_valid.empty:
        return None
    
    top_counts = df_valid['applicant_name'].value_counts().head(10)
    
    if top_counts.empty:
        return None
    
    plt.figure(figsize=(14,8))
    colors = random_palette(len(top_counts))
    top_counts.plot(kind='bar', color=colors, width=0.6)
    plt.title("Top Applicants by Submission Count")
    plt.xlabel("Applicant Name")
    plt.ylabel("Number of Submissions")
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    return fig_to_base64()

# 9️⃣ Percentage of Certificates Received
def plot_certificate_received_percentage_a(df):
    if df.empty or 'certificate_received' not in df.columns:
        return None
    
    df_valid = df[df['certificate_received'].notna()]
    
    if df_valid.empty:
        return None
    
    counts = df_valid['certificate_received'].value_counts(normalize=True) * 100
    
    if counts.empty:
        return None
    
    plt.figure(figsize=(10,10))
    counts.plot(kind='pie', autopct='%1.1f%%', colors=random_palette(len(counts)))
    plt.title("Percentage of Certificates Received")
    plt.ylabel("")
    plt.tight_layout()
    return fig_to_base64()

# 🔟 Review Recommendation Comparison (Primary vs Secondary)
def plot_review_recommendation_comparison_a(df):
    if df.empty or 'review_recommendation1' not in df.columns or 'review_recommendation' not in df.columns:
        return None
    
    df_valid = df[df['review_recommendation1'].notna() & df['review_recommendation'].notna()]
    
    if df_valid.empty:
        return None
    
    plt.figure(figsize=(14,8))
    categories = df_valid['review_recommendation1'].nunique()
    palette = random_palette(categories)
    sns.countplot(x="review_recommendation1", hue="review_recommendation", data=df_valid, palette=palette, dodge=True)
    plt.title("Primary vs Secondary Review Recommendation")
    plt.xlabel("Primary Recommendation")
    plt.ylabel("Count")
    plt.xticks(rotation=45, ha='right')
    plt.legend(title="Secondary Recommendation")
    plt.tight_layout()
    return fig_to_base64()

# 1️⃣1️⃣ Number of Applications Received vs Number of Certificates Issued
def plot_applications_vs_certificates_a(df):
    # Deduplicate by form ID so each application is counted only once
    df_unique = df.drop_duplicates(subset=['id'])
    
    applications_count = len(df_unique)  # total unique applications
    certificates_count = df_unique['certificate_issued'].notna().sum()  # issued certificates
    
    data = pd.DataFrame({
        'Category': ['Applications Received', 'Certificates Issued'],
        'Count': [applications_count, certificates_count]
    })
    
    plt.figure(figsize=(12,8))
    sns.barplot(x='Category', y='Count', data=data, palette=random_palette(2), width=0.6)
    plt.title("Applications Received vs Certificates Issued")
    return fig_to_base64()



###
### PLOT FORM B - ENHANCED ANALYTICS
###

def calculate_kpis_b(df):
    """Calculate KPIs for Form B with professional metrics"""
    # Use timezone-naive datetime to avoid comparison issues
    now = pd.Timestamp.now()
    current_month = now.to_period('M')
    
    # Basic metrics
    total_applications = len(df)
    
    # This month's applications
    df['submitted_at'] = pd.to_datetime(df['submitted_at'], errors='coerce')
    
    # Remove timezone info if present
    if df['submitted_at'].dt.tz is not None:
        df['submitted_at'] = df['submitted_at'].dt.tz_localize(None)
    
    this_month_apps = df[df['submitted_at'].dt.to_period('M') == current_month]
    this_month = len(this_month_apps)
    
    # Previous month for growth calculation
    prev_month = (current_month - 1)
    prev_month_apps = df[df['submitted_at'].dt.to_period('M') == prev_month]
    prev_month_count = len(prev_month_apps)
    
    # Growth rate calculation
    if prev_month_count > 0:
        growth_rate = ((this_month - prev_month_count) / prev_month_count) * 100
    else:
        growth_rate = 0 if this_month == 0 else 100
    
    # Certificate metrics
    certificates_issued = len(df[df['certificate_issued'] == True])
    certificates_received = len(df[df['certificate_received'] == True])
    
    # Completion rate (applications that got certificates)
    completion_rate = (certificates_issued / total_applications * 100) if total_applications > 0 else 0
    
    # High risk applications
    high_risk_count = len(df[df['risk_rating'].isin(['High', 'high', 'HIGH'])])
    
    # Average processing time (days from submission to certificate)
    df_with_cert = df[df['certificate_issued'] == True].copy()
    if len(df_with_cert) > 0 and 'review_signature_date' in df_with_cert.columns:
        df_with_cert['processing_days'] = (
            pd.to_datetime(df_with_cert['review_signature_date']) - 
            pd.to_datetime(df_with_cert['submitted_at'])
        ).dt.days
        avg_processing_days = df_with_cert['processing_days'].mean()
    else:
        avg_processing_days = 0
    
    return {
        'total_applications': total_applications,
        'this_month': this_month,
        'growth_rate': round(growth_rate, 1),
        'certificates_issued': certificates_issued,
        'certificates_received': certificates_received,
        'completion_rate': round(completion_rate, 1),
        'high_risk_count': high_risk_count,
        'avg_processing_days': round(avg_processing_days, 1) if avg_processing_days > 0 else 0
    }

def create_sunburst_chart_b(df):
    """Create interactive Sunburst chart for Form B application flow"""
    if df.empty:
        return "<div class='alert alert-info'>No data available for Sunburst chart</div>"
    
    # Prepare hierarchical data for Form B
    data_for_sunburst = []
    
    for _, row in df.iterrows():
        # Risk level
        risk_level = row.get('risk_rating', 'Unknown')
        
        # Supervisor recommendation
        supervisor_rec = row.get('supervisor_recommendation', 'Pending')
        
        # Review status
        review_rec = row.get('review_recommendation', 'Pending')
        
        # Final status
        if row.get('certificate_issued', False):
            final_status = 'Certificate Issued'
        elif review_rec not in ['Pending', None, '']:
            final_status = f'Review: {review_rec}'
        elif supervisor_rec not in ['Pending', None, '']:
            final_status = f'Supervisor: {supervisor_rec}'
        else:
            final_status = 'In Progress'
        
        data_for_sunburst.append({
            'ids': f"FormB-{risk_level}-{supervisor_rec}-{review_rec}-{final_status}",
            'labels': final_status,
            'parents': f"FormB-{risk_level}-{supervisor_rec}-{review_rec}",
            'values': 1
        })
        
        data_for_sunburst.append({
            'ids': f"FormB-{risk_level}-{supervisor_rec}-{review_rec}",
            'labels': f"Review: {review_rec}",
            'parents': f"FormB-{risk_level}-{supervisor_rec}",
            'values': 1
        })
        
        data_for_sunburst.append({
            'ids': f"FormB-{risk_level}-{supervisor_rec}",
            'labels': f"Supervisor: {supervisor_rec}",
            'parents': f"FormB-{risk_level}",
            'values': 1
        })
        
        data_for_sunburst.append({
            'ids': f"FormB-{risk_level}",
            'labels': f"Risk: {risk_level}",
            'parents': "Form B Applications",
            'values': 1
        })
    
    # Add root
    data_for_sunburst.append({
        'ids': "Form B Applications",
        'labels': "Form B Applications",
        'parents': "",
        'values': len(df)
    })
    
    # Convert to DataFrame and aggregate
    sunburst_df = pd.DataFrame(data_for_sunburst)
    sunburst_df = sunburst_df.groupby(['ids', 'labels', 'parents']).agg({'values': 'sum'}).reset_index()
    
    # Create Plotly Sunburst chart
    fig = go.Figure(go.Sunburst(
        ids=sunburst_df['ids'],
        labels=sunburst_df['labels'],
        parents=sunburst_df['parents'],
        values=sunburst_df['values'],
        branchvalues="total",
        hovertemplate='<b>%{label}</b><br>Applications: %{value}<br>Percentage: %{percentParent}<extra></extra>',
        maxdepth=4,
    ))
    
    fig.update_layout(
        title={
            'text': "Form B Application Flow - Hierarchical Analysis",
            'x': 0.5,
            'font': {'size': 18, 'color': '#1f5582'}
        },
        font=dict(size=12),
        width=800,
        height=600,
        margin=dict(t=80, l=20, r=20, b=20)
    )
    
    return fig.to_html(include_plotlyjs=True, div_id="sunburst-chart-b")

# 1️⃣ Count of Applications by Risk Rating - Enhanced Professional Version
def plot_risk_rating_distribution_b(df):
    """Enhanced professional risk rating distribution for Form B"""
    if df.empty:
        return "<div class='alert alert-info'>No Form B data available</div>"
    
    # Setup professional styling
    setup_professional_plot()
    
    plt.figure(figsize=(16,10))
    
    # Use risk_rating column (consistent with Form A)
    risk_col = 'risk_rating' if 'risk_rating' in df.columns else 'risk_level'
    
    # Count and sort risk levels
    risk_counts = df[risk_col].value_counts()
    
    # Create professional bar plot
    colors = [UJ_BRAND_COLORS['primary'], UJ_BRAND_COLORS['warning'], UJ_BRAND_COLORS['danger']]
    bars = plt.bar(risk_counts.index, risk_counts.values, color=colors[:len(risk_counts)], alpha=0.8, edgecolor='white', linewidth=1)
    
    # Add value labels on bars
    for bar, count in zip(bars, risk_counts.values):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                f'{count}\n({count/len(df)*100:.1f}%)', 
                ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    plt.title("Form B: Applications by Risk Rating", fontsize=16, fontweight='bold', pad=20, color='#1f5582')
    plt.xlabel("Risk Rating", fontsize=12, fontweight='bold')
    plt.ylabel("Number of Applications", fontsize=12, fontweight='bold')
    
    # Professional grid and styling
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    
    return fig_to_base64()

# 2️⃣ Review Recommendations Breakdown
def plot_review_recommendations_b(df):
    plt.figure(figsize=(12,8))
    categories = df['review_recommendation'].nunique()
    sns.countplot(x="review_recommendation", data=df, palette=random_palette(categories), width=0.6)
    plt.title("Review Recommendations")
    plt.xticks(rotation=45)
    return fig_to_base64()

# 3️⃣ Supervisor Recommendations Breakdown
def plot_supervisor_recommendations_b(df):
    plt.figure(figsize=(12,8))
    categories = df['supervisor_recommendation'].nunique()
    sns.countplot(x="supervisor_recommendation", data=df, palette=random_palette(categories), width=0.6)
    plt.title("Supervisor Recommendations")
    plt.xticks(rotation=45)
    return fig_to_base64()

# 4️⃣ Number of Applications per REC Member
def plot_rec_member_distribution_b(df):
    plt.figure(figsize=(12,8))
    categories = df['rec_full_name'].nunique()
    sns.countplot(y="rec_full_name", data=df, palette=random_palette(categories), width=0.6)
    plt.title("Applications Reviewed by Each REC Member")
    return fig_to_base64()

# 5️⃣ Certificate Issued vs Not Issued
def plot_certificate_status_b(df):
    plt.figure(figsize=(12,8))
    categories = df['certificate_issued'].nunique()
    sns.countplot(x="certificate_issued", data=df, palette=random_palette(categories), width=0.6)
    plt.title("Certificate Issuance Status")
    return fig_to_base64()

# 6️⃣ Applications Submitted Over Time
def plot_submissions_over_time_b(df):
    df['submitted_at'] = pd.to_datetime(df['submitted_at'], errors='coerce')
    plt.figure(figsize=(14,8))
    df.groupby(df['submitted_at'].dt.date).size().plot(kind='bar', color=random_palette(df['submitted_at'].dt.date.nunique()), width=0.6)
    plt.title("Submissions Over Time")
    plt.xlabel("Date")
    plt.ylabel("Number of Submissions")
    return fig_to_base64()

# 7️⃣ Review Recommendation by Risk Rating (stacked bar)
def plot_review_by_risk_rating_b(df):
    if df.empty or 'risk_level' not in df.columns:
        return None
    
    # Try both review_recommendation columns (primary and secondary)
    has_primary = 'review_recommendation' in df.columns
    has_secondary = 'review_recommendation1' in df.columns
    
    if not has_primary and not has_secondary:
        return None
    
    # Use whichever review recommendation column has more data
    if has_primary and has_secondary:
        primary_count = df['review_recommendation'].notna().sum()
        secondary_count = df['review_recommendation1'].notna().sum()
        review_col = 'review_recommendation' if primary_count >= secondary_count else 'review_recommendation1'
    elif has_primary:
        review_col = 'review_recommendation'
    else:
        review_col = 'review_recommendation1'
    
    # Remove rows with null values
    df_valid = df[df['risk_level'].notna() & df[review_col].notna()]
    
    if df_valid.empty:
        return None
    
    plt.figure(figsize=(14,8))
    review_risk = pd.crosstab(df_valid['risk_level'], df_valid[review_col])
    
    if review_risk.empty:
        return None
    
    colors = random_palette(review_risk.shape[1])
    review_risk.plot(kind='bar', stacked=True, ax=plt.gca(), color=colors, width=0.6)
    plt.title("Review Recommendation by Risk Rating")
    plt.xlabel("Risk Level")
    plt.ylabel("Count")
    plt.xticks(rotation=45, ha='right')
    plt.legend(title="Review Recommendation", bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    return fig_to_base64()

# 8️⃣ Top Applicants by Submission Count
def plot_top_applicants_b(df):
    plt.figure(figsize=(14,8))
    top_counts = df['applicant_name'].value_counts().head(10)
    colors = random_palette(len(top_counts))
    top_counts.plot(kind='bar', color=colors, width=0.6)
    plt.title("Top Applicants by Submission Count")
    return fig_to_base64()

# 9️⃣ Percentage of Certificates Received
def plot_certificate_received_percentage_b(df):
    plt.figure(figsize=(10,10))
    counts = df['certificate_received'].value_counts(normalize=True) * 100
    counts.plot(kind='pie', autopct='%1.1f%%', colors=random_palette(len(counts)))
    plt.title("Percentage of Certificates Received")
    plt.ylabel("")
    return fig_to_base64()

# 🔟 Review Recommendation Comparison (Primary vs Secondary)
def plot_review_recommendation_comparison_b(df):
    plt.figure(figsize=(14,8))
    categories = df['review_recommendation1'].nunique()
    palette = random_palette(categories)
    sns.countplot(x="review_recommendation1", hue="review_recommendation", data=df, palette=palette, dodge=True)
    plt.title("Primary vs Secondary Review Recommendation")
    plt.xticks(rotation=45)
    return fig_to_base64()


# 1️⃣1️⃣ Number of Applications Received vs Number of Certificates Issued
def plot_applications_vs_certificates_b(df):
    # Deduplicate by form ID so each application is counted only once
    df_unique = df.drop_duplicates(subset=['id'])
    
    applications_count = len(df_unique)  # total unique applications
    certificates_count = df_unique['certificate_issued'].notna().sum()  # issued certificates
    
    data = pd.DataFrame({
        'Category': ['Applications Received', 'Certificates Issued'],
        'Count': [applications_count, certificates_count]
    })
    
    plt.figure(figsize=(12,8))
    sns.barplot(x='Category', y='Count', data=data, palette=random_palette(2), width=0.6)
    plt.title("Applications Received vs Certificates Issued")
    return fig_to_base64()


###
### PLOT FORM C - ENHANCED ANALYTICS
###

def calculate_kpis_c(df):
    """Calculate KPIs for Form C with professional metrics"""
    # Use timezone-naive datetime to avoid comparison issues
    now = pd.Timestamp.now()
    current_month = now.to_period('M')
    
    # Basic metrics
    total_applications = len(df)
    
    # This month's applications
    df['submitted_at'] = pd.to_datetime(df['submitted_at'], errors='coerce')
    
    # Remove timezone info if present
    if df['submitted_at'].dt.tz is not None:
        df['submitted_at'] = df['submitted_at'].dt.tz_localize(None)
    
    this_month_apps = df[df['submitted_at'].dt.to_period('M') == current_month]
    this_month = len(this_month_apps)
    
    # Previous month for growth calculation
    prev_month = (current_month - 1)
    prev_month_apps = df[df['submitted_at'].dt.to_period('M') == prev_month]
    prev_month_count = len(prev_month_apps)
    
    # Growth rate calculation
    if prev_month_count > 0:
        growth_rate = ((this_month - prev_month_count) / prev_month_count) * 100
    else:
        growth_rate = 0 if this_month == 0 else 100
    
    # Certificate metrics
    certificates_issued = len(df[df['certificate_issued'] == True])
    certificates_received = len(df[df['certificate_received'] == True])
    
    # Completion rate (applications that got certificates)
    completion_rate = (certificates_issued / total_applications * 100) if total_applications > 0 else 0
    
    # High risk applications
    high_risk_count = len(df[df['risk_rating'].isin(['High', 'high', 'HIGH'])])
    
    # Average processing time (days from submission to certificate)
    df_with_cert = df[df['certificate_issued'] == True].copy()
    if len(df_with_cert) > 0 and 'review_signature_date' in df_with_cert.columns:
        df_with_cert['processing_days'] = (
            pd.to_datetime(df_with_cert['review_signature_date']) - 
            pd.to_datetime(df_with_cert['submitted_at'])
        ).dt.days
        avg_processing_days = df_with_cert['processing_days'].mean()
    else:
        avg_processing_days = 0
    
    return {
        'total_applications': total_applications,
        'this_month': this_month,
        'growth_rate': round(growth_rate, 1),
        'certificates_issued': certificates_issued,
        'certificates_received': certificates_received,
        'completion_rate': round(completion_rate, 1),
        'high_risk_count': high_risk_count,
        'avg_processing_days': round(avg_processing_days, 1) if avg_processing_days > 0 else 0
    }

def create_sunburst_chart_c(df):
    """Create interactive Sunburst chart for Form C application flow"""
    if df.empty:
        return "<div class='alert alert-info'>No data available for Sunburst chart</div>"
    
    # Prepare hierarchical data for Form C
    data_for_sunburst = []
    
    for _, row in df.iterrows():
        # Risk level
        risk_level = row.get('risk_rating', 'Unknown')
        
        # Supervisor recommendation
        supervisor_rec = row.get('supervisor_recommendation', 'Pending')
        
        # Review status
        review_rec = row.get('review_recommendation', 'Pending')
        
        # Final status
        if row.get('certificate_issued', False):
            final_status = 'Certificate Issued'
        elif review_rec not in ['Pending', None, '']:
            final_status = f'Review: {review_rec}'
        elif supervisor_rec not in ['Pending', None, '']:
            final_status = f'Supervisor: {supervisor_rec}'
        else:
            final_status = 'In Progress'
        
        data_for_sunburst.append({
            'ids': f"FormC-{risk_level}-{supervisor_rec}-{review_rec}-{final_status}",
            'labels': final_status,
            'parents': f"FormC-{risk_level}-{supervisor_rec}-{review_rec}",
            'values': 1
        })
        
        data_for_sunburst.append({
            'ids': f"FormC-{risk_level}-{supervisor_rec}-{review_rec}",
            'labels': f"Review: {review_rec}",
            'parents': f"FormC-{risk_level}-{supervisor_rec}",
            'values': 1
        })
        
        data_for_sunburst.append({
            'ids': f"FormC-{risk_level}-{supervisor_rec}",
            'labels': f"Supervisor: {supervisor_rec}",
            'parents': f"FormC-{risk_level}",
            'values': 1
        })
        
        data_for_sunburst.append({
            'ids': f"FormC-{risk_level}",
            'labels': f"Risk: {risk_level}",
            'parents': "Form C Applications",
            'values': 1
        })
    
    # Add root
    data_for_sunburst.append({
        'ids': "Form C Applications",
        'labels': "Form C Applications",
        'parents': "",
        'values': len(df)
    })
    
    # Convert to DataFrame and aggregate
    sunburst_df = pd.DataFrame(data_for_sunburst)
    sunburst_df = sunburst_df.groupby(['ids', 'labels', 'parents']).agg({'values': 'sum'}).reset_index()
    
    # Create Plotly Sunburst chart
    fig = go.Figure(go.Sunburst(
        ids=sunburst_df['ids'],
        labels=sunburst_df['labels'],
        parents=sunburst_df['parents'],
        values=sunburst_df['values'],
        branchvalues="total",
        hovertemplate='<b>%{label}</b><br>Applications: %{value}<br>Percentage: %{percentParent}<extra></extra>',
        maxdepth=4,
    ))
    
    fig.update_layout(
        title={
            'text': "Form C Application Flow - Hierarchical Analysis",
            'x': 0.5,
            'font': {'size': 18, 'color': '#1f5582'}
        },
        font=dict(size=12),
        width=800,
        height=600,
        margin=dict(t=80, l=20, r=20, b=20)
    )
    
    return fig.to_html(include_plotlyjs=True, div_id="sunburst-chart-c")

# 1️⃣ Count of Applications by Risk Rating - Enhanced Professional Version
def plot_risk_rating_distribution_c(df):
    """Enhanced professional risk rating distribution for Form C"""
    if df.empty:
        return "<div class='alert alert-info'>No Form C data available</div>"
    
    # Setup professional styling
    setup_professional_plot()
    
    plt.figure(figsize=(16,10))
    
    # Use risk_rating column (consistent with Form A)
    risk_col = 'risk_rating' if 'risk_rating' in df.columns else 'risk_level'
    
    # Count and sort risk levels
    risk_counts = df[risk_col].value_counts()
    
    # Create professional bar plot
    colors = [UJ_BRAND_COLORS['primary'], UJ_BRAND_COLORS['warning'], UJ_BRAND_COLORS['danger']]
    bars = plt.bar(risk_counts.index, risk_counts.values, color=colors[:len(risk_counts)], alpha=0.8, edgecolor='white', linewidth=1)
    
    # Add value labels on bars
    for bar, count in zip(bars, risk_counts.values):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                f'{count}\n({count/len(df)*100:.1f}%)', 
                ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    plt.title("Form C: Applications by Risk Rating", fontsize=16, fontweight='bold', pad=20, color='#1f5582')
    plt.xlabel("Risk Rating", fontsize=12, fontweight='bold')
    plt.ylabel("Number of Applications", fontsize=12, fontweight='bold')
    
    # Professional grid and styling
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    
    return fig_to_base64()

# 2️⃣ Review Recommendations Breakdown
def plot_review_recommendations_c(df):
    """Enhanced review recommendations for Form C"""
    if df.empty:
        return "<div class='alert alert-info'>No Form C data available</div>"
    
    # Setup professional styling
    setup_professional_plot()
    
    plt.figure(figsize=(16,10))
    
    # Check if column exists
    if 'review_recommendation' not in df.columns:
        return "<div class='alert alert-warning'>No review recommendation data available</div>"
    
    # Count and sort recommendations
    rec_counts = df['review_recommendation'].value_counts()
    
    # Create professional bar plot
    colors = [UJ_BRAND_COLORS['success'], UJ_BRAND_COLORS['warning'], UJ_BRAND_COLORS['danger']]
    bars = plt.bar(rec_counts.index, rec_counts.values, color=colors[:len(rec_counts)], alpha=0.8, edgecolor='white', linewidth=1)
    
    # Add value labels on bars
    for bar, count in zip(bars, rec_counts.values):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                f'{count}\n({count/len(df)*100:.1f}%)', 
                ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    plt.title("Form C: Review Recommendations", fontsize=16, fontweight='bold', pad=20, color='#1f5582')
    plt.xlabel("Recommendation", fontsize=12, fontweight='bold')
    plt.ylabel("Number of Applications", fontsize=12, fontweight='bold')
    
    plt.tight_layout()
    plt.xticks(rotation=45)
    return fig_to_base64()

# 3️⃣ Supervisor Recommendations Breakdown
def plot_supervisor_recommendations_c(df):
    """Enhanced supervisor recommendations for Form C"""
    if df.empty:
        return "<div class='alert alert-info'>No Form C data available</div>"
    
    # Setup professional styling
    setup_professional_plot()
    
    plt.figure(figsize=(16,10))
    
    # Check if column exists
    if 'supervisor_recommendation' not in df.columns:
        return "<div class='alert alert-warning'>No supervisor recommendation data available</div>"
    
    # Count and sort recommendations
    sup_counts = df['supervisor_recommendation'].value_counts()
    
    # Create professional bar plot
    colors = [UJ_BRAND_COLORS['success'], UJ_BRAND_COLORS['warning'], UJ_BRAND_COLORS['danger']]
    bars = plt.bar(sup_counts.index, sup_counts.values, color=colors[:len(sup_counts)], alpha=0.8, edgecolor='white', linewidth=1)
    
    # Add value labels on bars
    for bar, count in zip(bars, sup_counts.values):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                f'{count}\n({count/len(df)*100:.1f}%)', 
                ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    plt.title("Form C: Supervisor Recommendations", fontsize=16, fontweight='bold', pad=20, color='#1f5582')
    plt.xlabel("Recommendation", fontsize=12, fontweight='bold')
    plt.ylabel("Number of Applications", fontsize=12, fontweight='bold')
    
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    return fig_to_base64()

# 4️⃣ Number of Applications per REC Member
def plot_rec_member_distribution_c(df):
    """Enhanced REC member distribution for Form C"""
    if df.empty:
        return "<div class='alert alert-info'>No Form C data available</div>"
    
    # Setup professional styling
    setup_professional_plot()
    
    plt.figure(figsize=(12, 8))
    
    # Check if column exists
    if 'rec_full_name' not in df.columns:
        return "<div class='alert alert-warning'>No REC member data available</div>"
    
    # Count and sort REC members
    rec_counts = df['rec_full_name'].value_counts()
    
    if rec_counts.empty:
        return "<div class='alert alert-warning'>No REC member assignments found</div>"
    
    # Create professional horizontal bar plot
    y_pos = range(len(rec_counts))
    colors = get_professional_palette(len(rec_counts))
    bars = plt.barh(y_pos, rec_counts.values, color=colors, alpha=0.8, edgecolor='white', linewidth=1)
    
    # Add value labels on bars
    for i, (bar, count) in enumerate(zip(bars, rec_counts.values)):
        width = bar.get_width()
        plt.text(width + 0.1, bar.get_y() + bar.get_height()/2.,
                f'{count}', ha='left', va='center', fontweight='bold', fontsize=11)
    
    plt.title("Form C: Applications Reviewed by Each REC Member", fontsize=16, fontweight='bold', pad=20, color='#1f5582')
    plt.xlabel("Number of Applications", fontsize=12, fontweight='bold')
    plt.ylabel("REC Member", fontsize=12, fontweight='bold')
    
    # Set y-tick labels
    plt.yticks(y_pos, rec_counts.index)
    plt.tight_layout()
    return fig_to_base64()

# 5️⃣ Certificate Issued vs Not Issued
def plot_certificate_status_c(df):
    """Enhanced certificate status for Form C"""
    if df.empty:
        return "<div class='alert alert-info'>No Form C data available</div>"
    
    # Setup professional styling
    setup_professional_plot()
    
    plt.figure(figsize=(16,10))
    
    # Check if column exists
    if 'certificate_issued' not in df.columns:
        return "<div class='alert alert-warning'>No certificate status data available</div>"
    
    # Count and sort certificate status
    cert_counts = df['certificate_issued'].value_counts()
    
    # Create professional bar plot
    colors = [UJ_BRAND_COLORS['success'], UJ_BRAND_COLORS['danger']]
    bars = plt.bar(cert_counts.index, cert_counts.values, color=colors[:len(cert_counts)], alpha=0.8, edgecolor='white', linewidth=1)
    
    # Add value labels on bars
    for bar, count in zip(bars, cert_counts.values):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                f'{count}\n({count/len(df)*100:.1f}%)', 
                ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    plt.title("Form C: Certificate Issuance Status", fontsize=16, fontweight='bold', pad=20, color='#1f5582')
    plt.xlabel("Certificate Status", fontsize=12, fontweight='bold')
    plt.ylabel("Number of Applications", fontsize=12, fontweight='bold')
    
    plt.tight_layout()
    return fig_to_base64()

# 6️⃣ Applications Submitted Over Time
def plot_submissions_over_time_c(df):
    """Enhanced submissions over time for Form C with error handling"""
    if df.empty:
        return "<div class='alert alert-info'>No Form C data available</div>"
    
    # Check for submission_date column
    date_col = None
    for col_name in ['submission_date', 'submitted_at', 'created_at']:
        if col_name in df.columns:
            date_col = col_name
            break
    
    if date_col is None:
        return "<div class='alert alert-warning'>No date column found for submissions</div>"
    
    # Setup professional styling
    setup_professional_plot()
    
    plt.figure(figsize=(16,10))
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    
    # Filter out invalid dates
    valid_dates = df.dropna(subset=[date_col])
    if valid_dates.empty:
        return "<div class='alert alert-warning'>No valid submission dates found</div>"
    
    # Group by date and plot
    submission_counts = valid_dates.groupby(valid_dates[date_col].dt.date).size()
    
    bars = plt.bar(range(len(submission_counts)), submission_counts.values, 
                   color=UJ_BRAND_COLORS['primary'], alpha=0.8, edgecolor='white', linewidth=1)
    
    # Add value labels on bars
    for i, (bar, count) in enumerate(zip(bars, submission_counts.values)):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                f'{count}', ha='center', va='bottom', fontweight='bold', fontsize=10)
    
    plt.title("Form C: Submissions Over Time", fontsize=16, fontweight='bold', pad=20, color='#1f5582')
    plt.xlabel("Date", fontsize=12, fontweight='bold')
    plt.ylabel("Number of Submissions", fontsize=12, fontweight='bold')
    
    # Format x-axis
    plt.xticks(range(len(submission_counts)), 
               [str(date) for date in submission_counts.index], 
               rotation=45, ha='right')
    
    plt.tight_layout()
    plt.ylabel("Number of Submissions")
    return fig_to_base64()

# 7️⃣ Review Recommendation by Risk Rating (stacked bar)
def plot_review_by_risk_rating_c(df):
    """Enhanced review recommendations by risk rating for Form C with error handling"""
    if df.empty or 'risk_level' not in df.columns:
        return None
    
    # Try both review_recommendation columns (primary and secondary)
    has_primary = 'review_recommendation' in df.columns
    has_secondary = 'review_recommendation1' in df.columns
    
    if not has_primary and not has_secondary:
        return None
    
    # Use whichever review recommendation column has more data
    if has_primary and has_secondary:
        primary_count = df['review_recommendation'].notna().sum()
        secondary_count = df['review_recommendation1'].notna().sum()
        review_col = 'review_recommendation' if primary_count >= secondary_count else 'review_recommendation1'
    elif has_primary:
        review_col = 'review_recommendation'
    else:
        review_col = 'review_recommendation1'
    
    # Remove rows with null values
    df_valid = df[df['risk_level'].notna() & df[review_col].notna()]
    
    if df_valid.empty:
        return None
    
    plt.figure(figsize=(16,10))
    
    # Create crosstab for stacked analysis
    try:
        review_risk = pd.crosstab(df_valid['risk_level'], df_valid[review_col])
        
        if review_risk.empty:
            return None
        
        # Create professional stacked bar plot
        colors = list(UJ_BRAND_COLORS.values())[:review_risk.shape[1]]
        ax = review_risk.plot(kind='bar', stacked=True, figsize=(16,10), 
                             color=colors, alpha=0.8, edgecolor='white', linewidth=1)
        
        # Professional styling
        plt.title("Form C: Review Recommendations by Risk Rating", fontsize=16, fontweight='bold', pad=20, color='#1f5582')
        plt.xlabel("Risk Level", fontsize=12, fontweight='bold')
        plt.ylabel("Number of Applications", fontsize=12, fontweight='bold')
        
        # Rotate x-axis labels for better readability
        plt.xticks(rotation=45, ha='right')
        
        # Add legend with professional styling
        plt.legend(title="Review Recommendation", bbox_to_anchor=(1.05, 1), loc='upper left', 
                  frameon=True, fancybox=True, shadow=True)
        
        plt.tight_layout()
        return fig_to_base64()
        
    except Exception as e:
        print(f"Error creating review by risk rating chart: {e}")
        return None
        plt.tight_layout()
        
    except Exception as e:
        print(f"Error creating risk rating plot: {e}")
        return "<div class='alert alert-danger'>Error generating risk rating analysis</div>"
    
    return fig_to_base64()
    

# 8️⃣ Top Applicants by Submission Count
def plot_top_applicants_c(df):
    """Enhanced top applicants analysis for Form C with error handling"""
    if df.empty:
        return "<div class='alert alert-info'>No Form C data available</div>"
    
    # Check if applicant_name column exists
    if 'applicant_name' not in df.columns:
        return "<div class='alert alert-warning'>No applicant name data available</div>"
    
    # Setup professional styling
    setup_professional_plot()
    
    plt.figure(figsize=(16,10))
    
    # Get top applicants
    top_counts = df['applicant_name'].value_counts().head(10)
    
    if top_counts.empty:
        return "<div class='alert alert-warning'>No applicant data available</div>"
    
    # Create professional bar plot
    bars = plt.bar(range(len(top_counts)), top_counts.values, 
                   color=UJ_BRAND_COLORS['primary'], alpha=0.8, edgecolor='white', linewidth=1)
    
    # Add value labels on bars
    for i, (bar, count) in enumerate(zip(bars, top_counts.values)):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                f'{count}', ha='center', va='bottom', fontweight='bold', fontsize=10)
    
    plt.title("Form C: Top Applicants by Submission Count", fontsize=16, fontweight='bold', pad=20, color='#1f5582')
    plt.xlabel("Applicants", fontsize=12, fontweight='bold')
    plt.ylabel("Number of Submissions", fontsize=12, fontweight='bold')
    
    # Set x-axis labels
    plt.xticks(range(len(top_counts)), top_counts.index, rotation=45, ha='right')
    
    plt.tight_layout()
    return fig_to_base64()

# 9️⃣ Percentage of Certificates Received
def plot_certificate_received_percentage_c(df):
    """Enhanced certificate received percentage for Form C with error handling"""
    if df.empty:
        return "<div class='alert alert-info'>No Form C data available</div>"
    
    # Check if certificate_received column exists
    if 'certificate_received' not in df.columns:
        return "<div class='alert alert-warning'>No certificate received data available</div>"
    
    # Setup professional styling
    setup_professional_plot()
    
    plt.figure(figsize=(8, 8))
    
    # Calculate percentages
    counts = df['certificate_received'].value_counts(normalize=True) * 100
    
    if counts.empty:
        return "<div class='alert alert-warning'>No certificate data available</div>"
    
    # Create professional pie chart
    colors = [UJ_BRAND_COLORS['success'], UJ_BRAND_COLORS['danger']][:len(counts)]
    
    wedges, texts, autotexts = plt.pie(counts.values, labels=counts.index, autopct='%1.1f%%', 
                                      colors=colors, startangle=90, 
                                      textprops={'fontsize': 11, 'fontweight': 'bold'})
    
    # Style the percentage text
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(12)
    
    plt.title("Form C: Certificate Received Status", fontsize=16, fontweight='bold', pad=20, color='#1f5582')
    plt.axis('equal')  # Equal aspect ratio ensures pie chart is circular
    
    plt.tight_layout()
    return fig_to_base64()

# 🔟 Review Recommendation Comparison (Primary vs Secondary)
def plot_review_recommendation_comparison_c(df):
    plt.figure(figsize=(14,8))
    categories = df['review_recommendation1'].nunique()
    palette = random_palette(categories)
    sns.countplot(x="review_recommendation1", hue="review_recommendation", data=df, palette=palette, dodge=True)
    plt.title("Primary vs Secondary Review Recommendation")
    plt.xticks(rotation=45)
    return fig_to_base64()

# 1️⃣1️⃣ Number of Applications Received vs Number of Certificates Issued
def plot_applications_vs_certificates_c(df):
    # Deduplicate by form ID so each application is counted only once
    df_unique = df.drop_duplicates(subset=['id'])
    
    applications_count = len(df_unique)  # total unique applications
    certificates_count = df_unique['certificate_issued'].notna().sum()  # issued certificates
    
    data = pd.DataFrame({
        'Category': ['Applications Received', 'Certificates Issued'],
        'Count': [applications_count, certificates_count]
    })
    
    plt.figure(figsize=(12,8))
    sns.barplot(x='Category', y='Count', data=data, palette=random_palette(2), width=0.6)
    plt.title("Applications Received vs Certificates Issued")
    return fig_to_base64()


