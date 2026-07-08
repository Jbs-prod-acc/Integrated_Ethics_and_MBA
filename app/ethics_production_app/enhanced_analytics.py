import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import base64
import json
from datetime import datetime, timedelta
import numpy as np

# Set professional styling
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

# Professional color schemes
GOOGLE_COLORS = ['#4285F4', '#34A853', '#FBBC05', '#EA4335', '#9AA0A6', '#FF6D01', '#46BDC6']
UJ_COLORS = ['#022169', '#EF820D', '#1E90FF', '#32CD32', '#FFD700', '#FF6347', '#9370DB']

class AnalyticsDashboard:
    def __init__(self):
        self.style_config = {
            'font_family': 'Arial, sans-serif',
            'title_size': 16,
            'label_size': 12,
            'figure_size': (12, 8),
            'dpi': 100,
            'background_color': '#ffffff',
            'grid_alpha': 0.3
        }

    def create_plotly_chart(self, fig):
        """Convert Plotly figure to HTML div"""
        return fig.to_html(include_plotlyjs='cdn', div_id=f"chart_{np.random.randint(1000, 9999)}")

    def create_matplotlib_base64(self, fig=None):
        """Convert matplotlib figure to base64 string"""
        if fig is None:
            fig = plt.gcf()
        
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', bbox_inches='tight', 
                   facecolor='white', edgecolor='none', dpi=self.style_config['dpi'])
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close(fig)
        return img_base64

    def get_kpi_metrics(self, df, form_type='A'):
        """Calculate key performance indicators"""
        if df.empty:
            return {}
        
        total_applications = len(df.drop_duplicates(subset=['id'])) if 'id' in df.columns else len(df)
        
        # Date column mapping based on form type
        date_col = 'submitted_at' if form_type in ['A', 'B'] else 'submission_date'
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            # Strip timezone to avoid comparison issues
            if df[date_col].dt.tz is not None:
                df[date_col] = df[date_col].dt.tz_localize(None)
            
            # Calculate time-based metrics using naive datetime
            now = datetime.now()
            last_30_days = df[df[date_col] >= (now - timedelta(days=30))]
            this_month = len(last_30_days)
            
            # Calculate growth rate
            prev_30_days = df[(df[date_col] >= (now - timedelta(days=60))) & 
                             (df[date_col] < (now - timedelta(days=30)))]
            prev_month = len(prev_30_days)
            growth_rate = ((this_month - prev_month) / prev_month * 100) if prev_month > 0 else 0
        else:
            this_month = total_applications
            growth_rate = 0

        # Certificate metrics
        certificates_issued = df['certificate_issued'].notna().sum() if 'certificate_issued' in df.columns else 0
        certificates_received = df['certificate_received'].sum() if 'certificate_received' in df.columns else 0
        
        # Risk distribution
        risk_col = 'risk_rating' if 'risk_rating' in df.columns else 'risk_level'
        high_risk = len(df[df[risk_col].str.contains('High|high', na=False)]) if risk_col in df.columns else 0
        
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
            'high_risk_count': high_risk,
            'avg_processing_time': self._calculate_avg_processing_time(df, date_col)
        }

    def _calculate_avg_processing_time(self, df, date_col):
        """Calculate average processing time in days"""
        if date_col not in df.columns or 'certificate_issued' not in df.columns:
            return 0
        
        completed = df[df['certificate_issued'].notna() & df[date_col].notna()].copy()
        if len(completed) == 0:
            return 0
        
        # Assume certificate_issued is datetime, if not convert
        if not pd.api.types.is_datetime64_any_dtype(completed['certificate_issued']):
            completed.loc[:, 'certificate_issued'] = pd.to_datetime(completed['certificate_issued'], errors='coerce')
        
        # Strip timezone if present
        if completed[date_col].dt.tz is not None:
            completed.loc[:, date_col] = completed[date_col].dt.tz_localize(None)
        if completed['certificate_issued'].dt.tz is not None:
            completed.loc[:, 'certificate_issued'] = completed['certificate_issued'].dt.tz_localize(None)
        
        processing_times = (completed['certificate_issued'] - completed[date_col]).dt.days
        return round(processing_times.mean(), 1) if not processing_times.empty else 0

    def create_sunburst_chart(self, df, form_type='A'):
        """Create interactive sunburst chart for application flow"""
        if df.empty:
            return "<div>No data available</div>"
        
        # Prepare hierarchical data for sunburst
        risk_col = 'risk_rating' if 'risk_rating' in df.columns else 'risk_level'
        
        # Create hierarchy: Risk Level -> Review Status -> Certificate Status
        sunburst_data = []
        
        for risk in df[risk_col].dropna().unique():
            risk_df = df[df[risk_col] == risk]
            
            for review_status in ['Pending', 'Under Review', 'Approved', 'Rejected']:
                if 'review_recommendation' in df.columns:
                    if review_status == 'Approved':
                        status_df = risk_df[risk_df['review_recommendation'].str.contains('Approved', na=False)]
                    elif review_status == 'Rejected':
                        status_df = risk_df[risk_df['review_recommendation'].str.contains('Reject', na=False)]
                    elif review_status == 'Under Review':
                        status_df = risk_df[risk_df['review_recommendation'].notna() & 
                                          ~risk_df['review_recommendation'].str.contains('Approved|Reject', na=False)]
                    else:  # Pending
                        status_df = risk_df[risk_df['review_recommendation'].isna()]
                else:
                    status_df = risk_df
                
                if len(status_df) > 0:
                    sunburst_data.append({
                        'ids': f"{risk}-{review_status}",
                        'labels': review_status,
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
            return "<div>No data available for sunburst chart</div>"

        fig = go.Figure(go.Sunburst(
            ids=[item['ids'] for item in sunburst_data],
            labels=[item['labels'] for item in sunburst_data],
            parents=[item['parents'] for item in sunburst_data],
            values=[item['values'] for item in sunburst_data],
            branchvalues="total",
            hovertemplate='<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percentParent}<extra></extra>',
            maxdepth=3,
        ))

        fig.update_layout(
            title=f"Form {form_type} Application Flow Analysis",
            font_size=12,
            height=500,
            margin=dict(t=50, l=0, r=0, b=0)
        )

        return self.create_plotly_chart(fig)

    def create_interactive_timeline(self, df, form_type='A'):
        """Create interactive timeline of submissions"""
        if df.empty:
            return "<div>No data available</div>"
        
        date_col = 'submitted_at' if form_type in ['A', 'B'] else 'submission_date'
        
        if date_col not in df.columns:
            return "<div>Date column not found</div>"
        
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df_clean = df[df[date_col].notna()]
        
        if df_clean.empty:
            return "<div>No valid dates found</div>"
        
        # Group by date and count submissions
        daily_submissions = df_clean.groupby(df_clean[date_col].dt.date).size().reset_index()
        daily_submissions.columns = ['date', 'count']
        
        # Add cumulative count
        daily_submissions['cumulative'] = daily_submissions['count'].cumsum()
        
        # Create subplot with secondary y-axis
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # Add daily submissions bar chart
        fig.add_trace(
            go.Bar(
                x=daily_submissions['date'],
                y=daily_submissions['count'],
                name="Daily Submissions",
                marker_color=UJ_COLORS[1],
                opacity=0.7
            ),
            secondary_y=False
        )
        
        # Add cumulative line
        fig.add_trace(
            go.Scatter(
                x=daily_submissions['date'],
                y=daily_submissions['cumulative'],
                name="Cumulative Total",
                line=dict(color=UJ_COLORS[0], width=3),
                mode='lines+markers'
            ),
            secondary_y=True
        )
        
        fig.update_xaxes(title_text="Date")
        fig.update_yaxes(title_text="Daily Submissions", secondary_y=False)
        fig.update_yaxes(title_text="Cumulative Total", secondary_y=True)
        
        fig.update_layout(
            title=f"Form {form_type} Submission Timeline",
            height=400,
            showlegend=True,
            hovermode='x unified'
        )
        
        return self.create_plotly_chart(fig)

    def create_advanced_risk_analysis(self, df, form_type='A'):
        """Create advanced risk analysis with multiple visualizations"""
        if df.empty:
            return "<div>No data available</div>"
        
        risk_col = 'risk_rating' if 'risk_rating' in df.columns else 'risk_level'
        
        if risk_col not in df.columns:
            return "<div>Risk column not found</div>"
        
        # Create subplots for comprehensive risk analysis
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Risk Distribution', 'Risk vs Review Time', 
                          'Risk vs Certificate Success', 'Risk Trend Over Time'),
            specs=[[{"type": "pie"}, {"type": "box"}],
                   [{"type": "bar"}, {"type": "scatter"}]]
        )
        
        # 1. Risk Distribution Pie Chart
        risk_counts = df[risk_col].value_counts()
        fig.add_trace(
            go.Pie(labels=risk_counts.index, values=risk_counts.values, name="Risk Distribution"),
            row=1, col=1
        )
        
        # 2. Risk vs Processing Time Box Plot (if we have processing time data)
        if 'certificate_issued' in df.columns:
            date_col = 'submitted_at' if form_type in ['A', 'B'] else 'submission_date'
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                df['certificate_issued'] = pd.to_datetime(df['certificate_issued'], errors='coerce')
                # Strip timezone if present
                if df[date_col].dt.tz is not None:
                    df[date_col] = df[date_col].dt.tz_localize(None)
                if df['certificate_issued'].dt.tz is not None:
                    df['certificate_issued'] = df['certificate_issued'].dt.tz_localize(None)
                df['processing_days'] = (df['certificate_issued'] - df[date_col]).dt.days
                
                for risk_level in df[risk_col].dropna().unique():
                    risk_data = df[df[risk_col] == risk_level]['processing_days'].dropna()
                    fig.add_trace(
                        go.Box(y=risk_data, name=risk_level, showlegend=False),
                        row=1, col=2
                    )
        
        # 3. Risk vs Certificate Success Rate
        if 'certificate_received' in df.columns:
            cert_success = df.groupby(risk_col)['certificate_received'].agg(['count', 'sum']).reset_index()
            cert_success['success_rate'] = cert_success['sum'] / cert_success['count'] * 100
            
            fig.add_trace(
                go.Bar(x=cert_success[risk_col], y=cert_success['success_rate'], 
                      name="Success Rate %", showlegend=False),
                row=2, col=1
            )
        
        # 4. Risk Trend Over Time
        date_col = 'submitted_at' if form_type in ['A', 'B'] else 'submission_date'
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            # Strip timezone if present
            if df[date_col].dt.tz is not None:
                df[date_col] = df[date_col].dt.tz_localize(None)
            monthly_risk = df.groupby([df[date_col].dt.to_period('M'), risk_col]).size().unstack(fill_value=0)
            
            for risk_level in monthly_risk.columns:
                fig.add_trace(
                    go.Scatter(x=monthly_risk.index.astype(str), y=monthly_risk[risk_level],
                             name=risk_level, mode='lines+markers'),
                    row=2, col=2
                )
        
        fig.update_layout(height=600, title_text=f"Form {form_type} Comprehensive Risk Analysis")
        
        return self.create_plotly_chart(fig)

    def create_reviewer_performance_dashboard(self, df, form_type='A'):
        """Create comprehensive reviewer performance analysis"""
        if df.empty:
            return "<div>No data available</div>"

        submit_col = 'submitted_at' if form_type in ['A', 'B'] else 'submission_date'
        if submit_col not in df.columns and 'submitted_at' in df.columns:
            submit_col = 'submitted_at'
        if submit_col not in df.columns:
            return "<div>No reviewer timing data available</div>"

        review_events = []
        slot_configs = [
            ('first_reviewer_name', 'review_signature_date', 'review_recommendation', 'Primary'),
            ('second_reviewer_name', 'review_signature_date1', 'review_recommendation1', 'Secondary'),
        ]

        for reviewer_col, date_col, recommendation_col, position in slot_configs:
            if reviewer_col not in df.columns:
                continue

            slot_df = df.copy()
            if date_col in slot_df.columns:
                slot_df[date_col] = pd.to_datetime(slot_df[date_col], errors='coerce')
            if recommendation_col in slot_df.columns:
                slot_df[recommendation_col] = slot_df[recommendation_col].fillna('')
            slot_df[submit_col] = pd.to_datetime(slot_df[submit_col], errors='coerce')

            completed_mask = slot_df[reviewer_col].notna()
            if date_col in slot_df.columns:
                completed_mask = completed_mask & (
                    slot_df[date_col].notna() | slot_df[recommendation_col].ne('')
                )
            else:
                completed_mask = completed_mask & slot_df[recommendation_col].ne('')

            completed_reviews = slot_df[completed_mask].copy()
            if completed_reviews.empty:
                continue

            if date_col in completed_reviews.columns and completed_reviews[date_col].dt.tz is not None:
                completed_reviews[date_col] = completed_reviews[date_col].dt.tz_localize(None)
            if completed_reviews[submit_col].dt.tz is not None:
                completed_reviews[submit_col] = completed_reviews[submit_col].dt.tz_localize(None)

            if date_col in completed_reviews.columns:
                completed_reviews['review_time_days'] = (
                    completed_reviews[date_col] - completed_reviews[submit_col]
                ).dt.days
            else:
                completed_reviews['review_time_days'] = np.nan

            completed_reviews['approved'] = completed_reviews[recommendation_col].str.contains('Approved', na=False)
            completed_reviews['position'] = position

            review_events.extend(
                completed_reviews[
                    [reviewer_col, 'review_time_days', 'approved', 'position']
                ].rename(columns={reviewer_col: 'reviewer'}).to_dict('records')
            )

        if not review_events:
            return "<div>No reviewer data available</div>"

        reviewer_events_df = pd.DataFrame(review_events)
        reviewer_df = (
            reviewer_events_df.groupby('reviewer', dropna=False)
            .agg(
                total_reviews=('reviewer', 'size'),
                avg_review_time=('review_time_days', 'mean'),
                approval_rate=('approved', 'mean'),
                positions=('position', lambda values: ', '.join(sorted(set(values))))
            )
            .reset_index()
        )
        reviewer_df['approval_rate'] = (reviewer_df['approval_rate'] * 100).round(1)
        reviewer_df['avg_review_time'] = reviewer_df['avg_review_time'].round(1)
        reviewer_df = reviewer_df.sort_values(['total_reviews', 'reviewer'], ascending=[False, True])
        
        # Create performance dashboard
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Review Volume', 'Average Review Time', 
                          'Approval Rates', 'Efficiency Score'),
            specs=[[{"type": "bar"}, {"type": "bar"}],
                   [{"type": "bar"}, {"type": "scatter"}]]
        )
        
        # Review Volume
        fig.add_trace(
            go.Bar(x=reviewer_df['reviewer'], y=reviewer_df['total_reviews'], 
                   name="Total Reviews", showlegend=False, marker_color=UJ_COLORS[0],
                   customdata=reviewer_df[['positions']].values,
                   hovertemplate='<b>%{x}</b><br>Total Reviews: %{y}<br>Roles: %{customdata[0]}<extra></extra>'),
            row=1, col=1
        )
        
        # Average Review Time
        fig.add_trace(
            go.Bar(x=reviewer_df['reviewer'], y=reviewer_df['avg_review_time'], 
                   name="Avg Days", showlegend=False, marker_color=UJ_COLORS[1],
                   customdata=reviewer_df[['positions']].values,
                   hovertemplate='<b>%{x}</b><br>Average Review Time: %{y} days<br>Roles: %{customdata[0]}<extra></extra>'),
            row=1, col=2
        )
        
        # Approval Rates
        fig.add_trace(
            go.Bar(x=reviewer_df['reviewer'], y=reviewer_df['approval_rate'], 
                   name="Approval %", showlegend=False, marker_color=UJ_COLORS[2],
                   customdata=reviewer_df[['positions']].values,
                   hovertemplate='<b>%{x}</b><br>Approval Rate: %{y}%<br>Roles: %{customdata[0]}<extra></extra>'),
            row=2, col=1
        )
        
        # Efficiency Score (inverse of time * volume)
        reviewer_df['efficiency'] = reviewer_df['total_reviews'] / (reviewer_df['avg_review_time'].fillna(0) + 1)
        fig.add_trace(
            go.Scatter(x=reviewer_df['total_reviews'], y=reviewer_df['avg_review_time'],
                      text=reviewer_df['reviewer'], mode='markers+text',
                      marker=dict(size=reviewer_df['approval_rate']/2, 
                                color=reviewer_df['efficiency'],
                                colorscale='Viridis', showscale=True),
                      customdata=reviewer_df[['positions']].values,
                      hovertemplate='<b>%{text}</b><br>Total Reviews: %{x}<br>Average Review Time: %{y} days<br>Roles: %{customdata[0]}<extra></extra>',
                      name="Efficiency", showlegend=False),
            row=2, col=2
        )
        
        fig.update_layout(height=600, title_text=f"Form {form_type} Reviewer Performance Dashboard")
        
        return self.create_plotly_chart(fig)

    def _calculate_reviewer_avg_time(self, df, date_col, form_type):
        """Calculate average review time for a reviewer"""
        if date_col not in df.columns:
            return 0
        
        # Work on a copy to avoid SettingWithCopyWarning
        df_copy = df.copy()
        df_copy[date_col] = pd.to_datetime(df_copy[date_col], errors='coerce')
        submit_col = 'submitted_at' if form_type in ['A', 'B'] else 'submission_date'
        
        if submit_col not in df_copy.columns:
            return 0
        
        df_copy[submit_col] = pd.to_datetime(df_copy[submit_col], errors='coerce')
        
        # Strip timezone if present
        if df_copy[date_col].dt.tz is not None:
            df_copy[date_col] = df_copy[date_col].dt.tz_localize(None)
        if df_copy[submit_col].dt.tz is not None:
            df_copy[submit_col] = df_copy[submit_col].dt.tz_localize(None)
        
        review_times = (df_copy[date_col] - df_copy[submit_col]).dt.days
        return round(review_times.mean(), 1) if not review_times.empty else 0

    def _calculate_approval_rate(self, df, recommendation_col):
        """Calculate approval rate for a reviewer"""
        if recommendation_col not in df.columns:
            return 0
        
        total = len(df[df[recommendation_col].notna()])
        if total == 0:
            return 0
        
        approved = len(df[df[recommendation_col].str.contains('Approved', na=False)])
        return round(approved / total * 100, 1)

# Instance for easy import
analytics = AnalyticsDashboard()
