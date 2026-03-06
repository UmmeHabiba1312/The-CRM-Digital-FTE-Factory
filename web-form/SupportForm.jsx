import React, { useState } from 'react';

const CATEGORIES = [
  { value: 'general',   label: 'General Question' },
  { value: 'technical', label: 'Technical Support' },
  { value: 'billing',   label: 'Billing Inquiry' },
  { value: 'bug_report',label: 'Bug Report' },
  { value: 'feedback',  label: 'Feedback' },
];

const PRIORITIES = [
  { value: 'low',    label: 'Low — Not urgent' },
  { value: 'medium', label: 'Medium — Need help soon' },
  { value: 'high',   label: 'High — Urgent issue' },
];

const INITIAL_FORM = {
  name: '', email: '', subject: '',
  category: 'general', priority: 'medium', message: '',
};

export default function SupportForm({ apiEndpoint = '/api/support/submit' }) {
  const [form, setForm]     = useState(INITIAL_FORM);
  const [status, setStatus] = useState('idle');  // idle | submitting | success | error
  const [ticketId, setTicketId] = useState(null);
  const [error, setError]   = useState(null);

  const handleChange = (e) =>
    setForm(prev => ({ ...prev, [e.target.name]: e.target.value }));

  const validate = () => {
    if (form.name.trim().length < 2)
      return setError('Please enter your name (at least 2 characters)'), false;
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email))
      return setError('Please enter a valid email address'), false;
    if (form.subject.trim().length < 5)
      return setError('Subject must be at least 5 characters'), false;
    if (form.message.trim().length < 10)
      return setError('Please describe your issue in more detail (at least 10 characters)'), false;
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    if (!validate()) return;
    setStatus('submitting');
    try {
      const res = await fetch(apiEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Submission failed');
      }
      const data = await res.json();
      setTicketId(data.ticket_id);
      setStatus('success');
    } catch (err) {
      setError(err.message);
      setStatus('error');
    }
  };

  /* ---------- Success screen ---------- */
  if (status === 'success') {
    return (
      <div className="max-w-2xl mx-auto p-6 bg-white rounded-lg shadow-md">
        <div className="text-center">
          <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Thank You!</h2>
          <p className="text-gray-600 mb-4">Your support request has been submitted successfully.</p>
          <div className="bg-gray-50 rounded-lg p-4 mb-4">
            <p className="text-sm text-gray-500">Your Ticket ID</p>
            <p className="text-lg font-mono font-bold text-gray-900">{ticketId}</p>
          </div>
          <p className="text-sm text-gray-500">
            Our AI assistant will respond to your email within 5 minutes.
          </p>
          <button
            onClick={() => { setStatus('idle'); setForm(INITIAL_FORM); }}
            className="mt-6 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Submit Another Request
          </button>
        </div>
      </div>
    );
  }

  /* ---------- Form ---------- */
  return (
    <div className="max-w-2xl mx-auto p-6 bg-white rounded-lg shadow-md">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Contact Support</h2>
      <p className="text-gray-600 mb-6">
        Fill out the form below and our AI-powered support team will get back to you shortly.
      </p>

      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">

        {/* Name */}
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
            Your Name *
          </label>
          <input
            id="name" name="name" type="text" required
            value={form.name} onChange={handleChange}
            placeholder="Jane Doe"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* Email */}
        <div>
          <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
            Email Address *
          </label>
          <input
            id="email" name="email" type="email" required
            value={form.email} onChange={handleChange}
            placeholder="jane@company.com"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* Subject */}
        <div>
          <label htmlFor="subject" className="block text-sm font-medium text-gray-700 mb-1">
            Subject *
          </label>
          <input
            id="subject" name="subject" type="text" required
            value={form.subject} onChange={handleChange}
            placeholder="Brief description of your issue"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* Category + Priority */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="category" className="block text-sm font-medium text-gray-700 mb-1">
              Category *
            </label>
            <select
              id="category" name="category"
              value={form.category} onChange={handleChange}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="priority" className="block text-sm font-medium text-gray-700 mb-1">
              Priority
            </label>
            <select
              id="priority" name="priority"
              value={form.priority} onChange={handleChange}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              {PRIORITIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>
        </div>

        {/* Message */}
        <div>
          <label htmlFor="message" className="block text-sm font-medium text-gray-700 mb-1">
            How can we help? *
          </label>
          <textarea
            id="message" name="message" required rows={6}
            value={form.message} onChange={handleChange}
            placeholder="Please describe your issue or question in detail..."
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
          />
          <p className="mt-1 text-sm text-gray-500">{form.message.length}/1000 characters</p>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={status === 'submitting'}
          className={`w-full py-3 px-4 rounded-lg font-medium text-white transition-colors ${
            status === 'submitting' ? 'bg-gray-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'
          }`}
        >
          {status === 'submitting' ? (
            <span className="flex items-center justify-center">
              <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Submitting...
            </span>
          ) : 'Submit Support Request'}
        </button>

        <p className="text-center text-sm text-gray-500">
          By submitting, you agree to our{' '}
          <a href="/privacy" className="text-blue-600 hover:underline">Privacy Policy</a>
        </p>
      </form>
    </div>
  );
}
