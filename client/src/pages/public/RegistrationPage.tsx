import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { eventsApi, FEATURED_EVENT_SLUG } from '../../api/events';
import { paymentsApi } from '../../api/payments';
import { clearRegistrationIdempotencyKey } from '../../api/registrations';
import { mapRegistration, mapTicket } from '../../api/serializers';
import { EventItem } from '../../types';
import { Navbar } from '../../components/common/Navbar';
import { Footer } from '../../components/common/Footer';
import { FestivalMotifs } from '../../components/common/FestivalMotifs';
import { FestivalPoster } from '../../components/common/FestivalPoster';
import {
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  Calendar,
  Clock,
  MapPin,
  AlertCircle,
} from 'lucide-react';

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => {
      open: () => void;
      on: (event: string, callback: (payload: Record<string, unknown>) => void) => void;
    };
  }
}

export const RegistrationPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [event, setEvent] = useState<EventItem | null>(null);
  const [loadingEvent, setLoadingEvent] = useState(true);
  const [eventLoadError, setEventLoadError] = useState('');

  // Wizard state
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const submittingRef = useRef(false);

  // Form state
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [organization, setOrganization] = useState('');
  const [jobTitle, setJobTitle] = useState('');
  const [selectedTierId, setSelectedTierId] = useState<string>('');
  const [attendeeNames, setAttendeeNames] = useState<string[]>([]);
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [readTerms, setReadTerms] = useState(false);

  // Field validation errors
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    eventsApi.getById(FEATURED_EVENT_SLUG).then((evt) => {
      if (cancelled) return;
      setEvent(evt);
      if (evt && evt.tiers.length > 0) {
        const queryTier = searchParams.get('tier');
        const defaultTier =
          evt.tiers.find((tier) => tier.id === queryTier && tier.available > 0) ||
          evt.tiers.find((tier) => tier.available > 0);
        setSelectedTierId(defaultTier?.id || '');
      }
      setLoadingEvent(false);
    }).catch((error: unknown) => {
      if (cancelled) return;
      setEventLoadError(error instanceof Error ? error.message : 'Unable to load event details. Please try again.');
      setLoadingEvent(false);
    });
    return () => { cancelled = true; };
  }, [searchParams]);

  useEffect(() => {
    if (document.getElementById('razorpay-checkout-script')) return;

    const script = document.createElement('script');
    script.id = 'razorpay-checkout-script';
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.async = true;
    document.body.appendChild(script);
  }, []);

  if (loadingEvent) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!event) {
    return (
      <div className="festival-public min-h-screen bg-slate-950 text-slate-100 flex flex-col">
        <Navbar />
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
          <h2 className="text-xl font-bold font-display text-white mb-2">{eventLoadError ? 'Event Unavailable' : 'Event Not Found'}</h2>
          {eventLoadError && <p role="alert" className="text-sm text-slate-400 mb-4">{eventLoadError}</p>}
          <button
            onClick={() => navigate('/events')}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs"
          >
            Back to Events
          </button>
        </div>
        <Footer />
      </div>
    );
  }

  const selectedTier = event.tiers.find((t) => t.id === selectedTierId) || event.tiers[0];
  const selectedAdmissionCount = selectedTier?.admissionCount ?? 1;
  const availablePackages = (tier: typeof event.tiers[number]) =>
    Math.min(tier.available, Math.floor((event.capacity - event.registeredCount) / (tier.admissionCount ?? 1)));
  const registrationAvailable =
    event.status === 'open' &&
    event.registeredCount < event.capacity &&
    event.tiers.some((tier) => availablePackages(tier) > 0);

  const clearFieldError = (field: string) => {
    setFieldErrors((current) => {
      if (!current[field]) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
  };

  const getFieldError = (field: 'fullName' | 'email' | 'phone', value: string) => {
    const normalizedValue = value.trim();

    if (field === 'fullName') {
      if (!normalizedValue) return 'Please enter your full name';
      if (!/^[\p{L}\p{M}]+(?:[ '\u2019-][\p{L}\p{M}]+)*$/u.test(normalizedValue)) {
        return 'Use letters only; spaces, apostrophes, and hyphens are allowed';
      }
    }

    if (field === 'email' && (!normalizedValue || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedValue))) {
      return 'Please enter a valid email address';
    }

    if (field === 'phone') {
      if (!/^[0-9]{10}$/.test(normalizedValue)) return 'Enter a 10-digit mobile number';
    }

    return '';
  };

  const validateField = (field: 'fullName' | 'email' | 'phone', value: string) => {
    const error = getFieldError(field, value);
    setFieldErrors((current) => {
      if (!error && !current[field]) return current;
      return { ...current, [field]: error };
    });
  };

  const validateStep1 = () => {
    const errors = {
      fullName: getFieldError('fullName', fullName),
      email: getFieldError('email', email),
      phone: getFieldError('phone', phone),
    };

    setFieldErrors(Object.fromEntries(Object.entries(errors).filter(([, error]) => error)));
    return Object.values(errors).every((error) => !error);
  };

  const handleNextStep1 = (e: React.FormEvent) => {
    e.preventDefault();
    if (validateStep1()) {
      setStep(2);
    }
  };

  const handleReviewTier = () => {
    if (selectedTier && selectedAdmissionCount > 1) {
      const names = [fullName, ...attendeeNames.slice(0, selectedAdmissionCount - 1)];
      const hasInvalidName = names.some((name) => getFieldError('fullName', name));
      if (hasInvalidName) {
        setErrorMessage(`Enter a valid name for each of the ${selectedAdmissionCount} attendees.`);
        return;
      }
    }
    setErrorMessage('');
    setStep(3);
  };

  const handleSubmitRegistration = async () => {
    if (submittingRef.current) return;
    if (!agreeTerms) {
      setErrorMessage('Please accept the event admission terms before confirming.');
      return;
    }

    if (!selectedTier) {
      setErrorMessage('Select an available ticket offer before continuing.');
      return;
    }

    submittingRef.current = true;
    setIsSubmitting(true);
    setErrorMessage('');

    try {
      const buyer = {
        name: fullName,
        email,
        phone: `+91${phone}`,
        organization: organization.trim() || '',
        job_title: jobTitle.trim() || '',
      };
      const registrationParams = {
        eventId: event.id,
        tierId: selectedTier.id,
        source: 'ONLINE' as const,
        attendee: {
          fullName: buyer.name,
          email: buyer.email,
          phone: buyer.phone,
          organization: buyer.organization,
          jobTitle: buyer.job_title,
        },
        attendeeNames:
          selectedAdmissionCount > 1
            ? [fullName, ...attendeeNames.slice(0, selectedAdmissionCount - 1)]
            : [fullName],
      };
      const order = await paymentsApi.createOrder(registrationParams);

      const showVerifiedRegistration = async (data: {
        registration: Parameters<typeof mapRegistration>[0];
        ticket?: Parameters<typeof mapTicket>[0];
        tickets: Parameters<typeof mapTicket>[0][];
      }) => {
        const tickets = data.tickets.map(mapTicket);
        const registration = mapRegistration(data.registration);
        navigate('/registration/success', {
          state: {
            registration,
            ticket: tickets[0] ?? (data.ticket ? mapTicket(data.ticket) : undefined),
            tickets,
          },
        });
      };

      const existingRegistration = order.registration;
      const existingTickets = order.tickets;
      if (order.payment_verified && existingRegistration && existingTickets) {
        await clearRegistrationIdempotencyKey(registrationParams);
        await showVerifiedRegistration({
          registration: existingRegistration,
          ticket: order.ticket,
          tickets: existingTickets,
        });
        return;
      }
      if (!order.key_id || !order.order_id || !order.amount || !order.currency) {
        throw new Error('Payment is not configured for this event right now. Please try again later.');
      }

      const recoveryKey = `ticketing.payment-recovery.${order.idempotency_key}`;
      const serializedRecovery = sessionStorage.getItem(recoveryKey);
      if (serializedRecovery) {
        let recovery: {
          order_id?: string;
          razorpay_order_id?: string;
          razorpay_payment_id?: string;
          razorpay_signature?: string;
        };
        try {
          recovery = JSON.parse(serializedRecovery) as typeof recovery;
        } catch {
          sessionStorage.removeItem(recoveryKey);
          recovery = {};
        }
        if (
          recovery.razorpay_order_id === order.order_id &&
          recovery.razorpay_payment_id &&
          recovery.razorpay_signature
        ) {
          const verified = await paymentsApi.verify({
            razorpay_order_id: recovery.razorpay_order_id,
            razorpay_payment_id: recovery.razorpay_payment_id,
            razorpay_signature: recovery.razorpay_signature,
          });
          sessionStorage.removeItem(recoveryKey);
          await clearRegistrationIdempotencyKey(registrationParams);
          await showVerifiedRegistration(verified);
          return;
        }
      }

      const Razorpay = window.Razorpay;
      if (!Razorpay) {
        throw new Error('Razorpay checkout is unavailable in this browser.');
      }

      let paymentCallbackStarted = false;
      const razorpayInstance = new Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: event.name,
        description: selectedTier.name,
        order_id: order.order_id,
        prefill: {
          name: fullName,
          email,
          contact: `+91${phone}`,
        },
        theme: {
          color: '#b71959',
        },
        handler: async (paymentResponse: Record<string, unknown>) => {
          if (paymentCallbackStarted) return;
          paymentCallbackStarted = true;
          let paymentVerified = false;
          try {
            const razorpayOrderId = paymentResponse.razorpay_order_id;
            const razorpayPaymentId = paymentResponse.razorpay_payment_id;
            const razorpaySignature = paymentResponse.razorpay_signature;
            if (
              typeof razorpayOrderId !== 'string' ||
              typeof razorpayPaymentId !== 'string' ||
              typeof razorpaySignature !== 'string'
            ) {
              throw new Error('Razorpay returned an incomplete payment response.');
            }
            sessionStorage.setItem(
              recoveryKey,
              JSON.stringify({
                razorpay_order_id: razorpayOrderId,
                razorpay_payment_id: razorpayPaymentId,
                razorpay_signature: razorpaySignature,
              }),
            );
            const verification = await paymentsApi.verify({
              razorpay_order_id: razorpayOrderId,
              razorpay_payment_id: razorpayPaymentId,
              razorpay_signature: razorpaySignature,
            });
            if (!verification.payment_verified) {
              throw new Error('Payment verification failed. Contact the event team before trying again.');
            }
            paymentVerified = true;
            sessionStorage.removeItem(recoveryKey);
            await clearRegistrationIdempotencyKey(registrationParams);
            await showVerifiedRegistration(verification);
          } catch (error: unknown) {
            setErrorMessage(
              paymentVerified
                ? `Payment was verified and your tickets are being prepared: ${error instanceof Error ? error.message : 'Unexpected error.'} Retry this registration with the same details to recover the confirmation.`
                : `We could not confirm the payment response: ${error instanceof Error ? error.message : 'Unexpected error.'} Your payment details have been retained for safe retry. Do not pay again until you retry this registration.`,
            );
            submittingRef.current = false;
            setIsSubmitting(false);
          }
        },
        modal: {
          ondismiss: () => {
            submittingRef.current = false;
            setIsSubmitting(false);
          },
        },
      });

      razorpayInstance.on('payment.failed', (failure: Record<string, unknown>) => {
        const details = failure.error;
        void paymentsApi.recordFailure({
          razorpay_order_id: order.order_id!,
        }).catch((error: unknown) => {
          console.error('Unable to record Razorpay payment failure.', error);
        });
        const message =
          typeof details === 'object' && details !== null
            ? 'description' in details && typeof details.description === 'string'
              ? details.description
              : 'reason' in details && typeof details.reason === 'string'
                ? details.reason
                : 'Payment failed. Please try again.'
            : 'Payment failed. Please try again.';
        setErrorMessage(message);
        submittingRef.current = false;
        setIsSubmitting(false);
      });

      razorpayInstance.open();
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Registration failed. Please try again.');
      submittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  return (
    <div className="festival-public min-h-screen flex flex-col bg-slate-950 text-slate-100">
      <Navbar />

      <main className="festival-hero flex-1 pt-32 pb-24 max-w-3xl mx-auto px-4 sm:px-6 w-full">
        <FestivalMotifs showDandiya={false} />
        {/* Event context header */}
        <div className="festival-card mb-8 p-4 bg-slate-900 border border-slate-800 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <FestivalPoster className="hidden w-24 shrink-0 sm:block" />
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-mono font-semibold text-indigo-400 uppercase tracking-wider">
              SOUNDARYA · ONLINE PASS PREVIEW
            </div>
            <h1 className="text-xl font-bold font-display text-white">{event.name}</h1>
            <p className="text-xs text-slate-400 flex flex-wrap items-center gap-2 mt-1">
              <Calendar className="w-3.5 h-3.5 text-indigo-400" />
              <span>{event.formattedDate}</span>
              <span>·</span>
              <Clock className="w-3.5 h-3.5 text-indigo-400" />
              <span>{event.time}</span>
              <span>·</span>
              <MapPin className="w-3.5 h-3.5 text-indigo-400" />
              <span>{event.venue}</span>
            </p>
          </div>
          <div className="text-right sm:border-l sm:border-slate-800 sm:pl-4">
            <span className="text-[10px] text-slate-500 uppercase font-semibold block">TIER</span>
            <span className="text-sm font-bold text-white font-mono">{selectedTier?.name}</span>
          </div>
        </div>
        {!registrationAvailable ? (
          <div className="rounded-2xl border border-amber-900/60 bg-amber-950/30 p-6 text-center">
            <h2 className="font-display text-lg font-bold text-white">Registration is unavailable</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-300">
              {event.status !== 'open'
                ? 'Registration is not open for this event.'
                : event.registeredCount >= event.capacity
                  ? 'This event has reached its registration capacity.'
                  : 'All ticket tiers are currently sold out.'}
            </p>
            <Link
              to={`/events/${event.slug}`}
              className="mt-4 inline-flex rounded-xl border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors hover:bg-slate-800"
            >
              Return to event
            </Link>
          </div>
        ) : (
          <>
        {/* 4-Step Progress Indicator */}
        <div className="mb-10">
          <div className="flex items-center justify-between text-xs font-mono mb-2">
            <span className={step >= 1 ? 'text-indigo-400 font-bold' : 'text-slate-500'}>
              01. Personal Details
            </span>
            <span className={step >= 2 ? 'text-indigo-400 font-bold' : 'text-slate-500'}>
              02. Pass Tier
            </span>
            <span className={step >= 3 ? 'text-indigo-400 font-bold' : 'text-slate-500'}>
              03. Review &amp; Confirm
            </span>
          </div>
          <div className="w-full bg-slate-900 h-1.5 rounded-full overflow-hidden border border-slate-800">
            <div
              className="bg-indigo-600 h-full transition-all duration-300"
              style={{ width: `${(step / 3) * 100}%` }}
            />
          </div>
        </div>

        {/* STEP 1: Personal Details */}
        {step === 1 && (
          <form
            onSubmit={handleNextStep1}
            className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6"
          >
            <div>
              <h2 className="text-lg font-bold font-display text-white">Attendee Information</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Please enter the details of the person who will be attending this event.
              </p>
            </div>

            <div className="space-y-4">
              <div>
                <label htmlFor="attendee-name" className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                  Full Name <span className="text-rose-400">*</span>
                </label>
                <input
                  id="attendee-name"
                  type="text"
                  required
                  maxLength={80}
                  value={fullName}
                  autoComplete="name"
                  onChange={(e) => {
                    setFullName(e.target.value);
                    clearFieldError('fullName');
                  }}
                  onBlur={(e) => validateField('fullName', e.target.value)}
                  placeholder="e.g. Rahul Sharma"
                  aria-invalid={Boolean(fieldErrors.fullName)}
                  aria-describedby={fieldErrors.fullName ? 'attendee-name-error' : undefined}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                {fieldErrors.fullName && (
                  <p id="attendee-name-error" className="text-xs text-rose-400 mt-1">{fieldErrors.fullName}</p>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="attendee-email" className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                    Email Address <span className="text-rose-400">*</span>
                  </label>
                  <input
                    id="attendee-email"
                    type="email"
                    required
                    maxLength={254}
                    autoComplete="email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      clearFieldError('email');
                    }}
                    onBlur={(e) => validateField('email', e.target.value)}
                    placeholder="name@company.com"
                    aria-invalid={Boolean(fieldErrors.email)}
                    aria-describedby={fieldErrors.email ? 'attendee-email-error' : undefined}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <p className="mt-1.5 text-[10px] text-slate-400">
                    Please provide a valid email ID, as your ticket will be received on this email.
                  </p>
                  {fieldErrors.email && (
                    <p id="attendee-email-error" className="text-xs text-rose-400 mt-1">{fieldErrors.email}</p>
                  )}
                </div>

                <div>
                  <label htmlFor="attendee-phone" className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                    Phone / Mobile <span className="text-rose-400">*</span>
                  </label>
                  <div className="flex overflow-hidden rounded-xl border border-slate-800 bg-slate-950 focus-within:ring-2 focus-within:ring-indigo-500">
                    <span className="flex items-center border-r border-slate-800 px-3 text-xs font-semibold text-slate-400" aria-hidden="true">
                      +91
                    </span>
                    <input
                      id="attendee-phone"
                      type="tel"
                      inputMode="numeric"
                      required
                      maxLength={10}
                      pattern="[0-9]{10}"
                      autoComplete="tel-national"
                      value={phone}
                      onChange={(e) => {
                        setPhone(e.target.value.replace(/\D/g, '').slice(0, 10));
                        clearFieldError('phone');
                      }}
                      onBlur={(e) => validateField('phone', e.target.value)}
                      placeholder="98450 00000"
                      aria-label="10-digit mobile number, country code +91"
                      aria-invalid={Boolean(fieldErrors.phone)}
                      aria-describedby={fieldErrors.phone ? 'attendee-phone-error' : undefined}
                      className="w-full min-w-0 bg-transparent px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none"
                    />
                  </div>
                  {fieldErrors.phone && (
                    <p id="attendee-phone-error" className="text-xs text-rose-400 mt-1">{fieldErrors.phone}</p>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                    Organization / Company / College
                  </label>
                  <input
                    type="text"
                    value={organization}
                    onChange={(e) => setOrganization(e.target.value)}
                    placeholder="e.g. Soundarya College"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                    Job Title / Role
                  </label>
                  <input
                    type="text"
                    value={jobTitle}
                    onChange={(e) => setJobTitle(e.target.value)}
                    placeholder="e.g. Student"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-slate-800 flex justify-end">
              <button
                type="submit"
                className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 text-white rounded-xl text-xs font-semibold inline-flex items-center gap-2 cursor-pointer transition-all shadow-md"
              >
                <span>Continue to Pass Tier</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </form>
        )}

        {/* STEP 2: Pass Tier Selection */}
        {step === 2 && (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6">
            <div>
              <h2 className="text-lg font-bold font-display text-white">Select Admission Tier</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Choose the pass that best fits your requirements for this event.
              </p>
            </div>

            <div className="space-y-3">
              {event.tiers.map((tier) => {
                const isSelected = tier.id === selectedTierId;
                return (
                  <button
                    type="button"
                    key={tier.id}
                    onClick={() => setSelectedTierId(tier.id)}
                    disabled={tier.available < 1}
                    aria-pressed={isSelected}
                    className={`w-full p-4 rounded-xl border text-left transition-all disabled:cursor-not-allowed disabled:opacity-50 ${
                      isSelected
                        ? 'bg-indigo-950/40 border-indigo-500 shadow-sm'
                        : 'bg-slate-950 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-3">
                        <div
                          className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                            isSelected ? 'border-indigo-500 bg-indigo-500' : 'border-slate-600'
                          }`}
                        >
                          {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                        </div>
                        <span className="font-semibold text-sm text-white">{tier.name}</span>
                      </div>
                      <span className="font-mono font-bold text-sm text-indigo-300">
                        ₹{tier.price}
                      </span>
                    </div>

                    <p className="pl-7 text-xs text-slate-400">{tier.description}</p>
                    <p className="pl-7 pt-1 text-[10px] font-mono text-slate-500">
                      {availablePackages(tier) > 0
                        ? `${availablePackages(tier)} ${(tier.admissionCount ?? 1) > 1 ? 'combo offers' : 'tickets'} available`
                        : 'SOLD OUT'}
                    </p>

                    <div className="pl-7 mt-2 flex flex-wrap gap-2">
                      {tier.perks.map((p, i) => (
                        <span
                          key={i}
                          className="text-[11px] text-slate-300 bg-slate-900 px-2 py-0.5 rounded border border-slate-800"
                        >
                          ✓ {p}
                        </span>
                      ))}
                    </div>
                  </button>
                );
              })}
            </div>

            {selectedTier && selectedAdmissionCount > 1 && (
              <section className="mt-6 border-t border-slate-800 pt-5" aria-labelledby="combo-attendees-heading">
                <h3 id="combo-attendees-heading" className="text-sm font-bold text-white">
                  Attendee names <span className="text-rose-400">*</span>
                </h3>
                <p className="mt-1 text-xs text-slate-400">
                  Enter the name for each of the {selectedAdmissionCount} individual tickets. Buyer email and mobile are shared.
                </p>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-slate-300">Attendee 1 name</label>
                    <p className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-2.5 text-xs text-white">{fullName}</p>
                  </div>
                  {Array.from({ length: selectedAdmissionCount - 1 }, (_, index) => (
                    <div key={index}>
                      <label htmlFor={`combo-attendee-${index + 2}`} className="mb-1.5 block text-xs font-semibold text-slate-300">
                        Attendee {index + 2} name <span className="text-rose-400">*</span>
                      </label>
                      <input
                        id={`combo-attendee-${index + 2}`}
                        type="text"
                        required
                        maxLength={80}
                        value={attendeeNames[index] ?? ''}
                        onChange={(e) => {
                          const nextNames = [...attendeeNames];
                          nextNames[index] = e.target.value;
                          setAttendeeNames(nextNames);
                          setErrorMessage('');
                        }}
                        placeholder={`Full name for ticket ${index + 2}`}
                        className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      />
                    </div>
                  ))}
                </div>
              </section>
            )}

            {errorMessage && (
              <p role="alert" className="text-xs text-rose-400">{errorMessage}</p>
            )}

            <div className="pt-4 border-t border-slate-800 flex justify-between items-center">
              <button
                type="button"
                onClick={() => {
                  setErrorMessage('');
                  setStep(1);
                }}
                className="px-4 py-2.5 text-xs text-slate-400 hover:text-white inline-flex items-center gap-1.5 cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Back</span>
              </button>

              <button
                type="button"
                onClick={handleReviewTier}
                disabled={!selectedTier || availablePackages(selectedTier) < 1}
                className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold inline-flex items-center gap-2 cursor-pointer transition-all shadow-md"
              >
                <span>Review Registration</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* STEP 3: Review & Confirmation */}
        {step === 3 && (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6">
            <div>
              <h2 className="text-lg font-bold font-display text-white">Review &amp; Finalize</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Confirm your registration details before issuing the digital ticket.
              </p>
            </div>

            {errorMessage && (
              <div className="p-3 bg-rose-950/60 border border-rose-800 rounded-xl flex items-center gap-2 text-xs text-rose-300">
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
                <span>{errorMessage}</span>
              </div>
            )}

            <div className="bg-slate-950 border border-slate-800 rounded-xl p-5 space-y-4">
              <div className="flex justify-between items-center pb-3 border-b border-slate-800">
                <div>
                  <span className="text-[10px] text-slate-500 font-semibold uppercase block">EVENT</span>
                  <span className="text-sm font-bold text-white">{event.name}</span>
                </div>
                <div className="text-right">
                  <span className="text-[10px] text-slate-500 font-semibold uppercase block">PASS TIER</span>
                  <span className="text-sm font-mono font-bold text-indigo-400">{selectedTier.name}</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-slate-500 block">Attendee Name</span>
                  <span className="text-slate-200 font-semibold">{fullName}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Email Address</span>
                  <span className="text-slate-200 font-semibold">{email}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Phone</span>
                  <span className="text-slate-200 font-mono">+91 {phone}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Organization</span>
                  <span className="text-slate-200">{organization || 'Independent'}</span>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-800 flex justify-between items-center text-xs">
                <span className="text-slate-400">
                  {selectedAdmissionCount > 1
                    ? `${selectedAdmissionCount - 1} tickets + 1 free • total`
                    : 'Total'}
                </span>
                <span className="text-lg font-bold font-mono text-white">
                  ₹{selectedTier.price}
                </span>
              </div>
            </div>

            <section aria-labelledby="terms-heading" className="space-y-3">
              <div>
                <h3 id="terms-heading" className="text-sm font-bold text-white">Terms &amp; Conditions</h3>
                <p className="mt-1 text-xs text-slate-400">
                  Read all the event rules below. Scroll to the end to enable agreement.
                </p>
              </div>
              <div
                role="region"
                aria-label="Terms and Conditions"
                tabIndex={0}
                onScroll={(e) => {
                  const element = e.currentTarget;
                  if (element.scrollTop + element.clientHeight >= element.scrollHeight - 4) {
                    setReadTerms(true);
                  }
                }}
                className="max-h-56 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/60 p-4 text-xs text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <ul className="list-disc space-y-2 pl-5">
                  <li>Carry your ticket and valid ID. Arrive 1 hour early for entry and security checking.</li>
                  <li>Tickets are non-transferable and non-refundable. No re-entry after exit.</li>
                  <li>One pair of Dandiya sticks and refreshments are included with each ticket.</li>
                  <li>Traditional/ethnic wear is recommended.</li>
                  <li>Outside food, beverages, and water bottles are not allowed.</li>
                  <li>Alcohol, smoking, drugs, weapons, and sharp objects are strictly prohibited.</li>
                  <li>Security and bag checks will be conducted at the entrance.</li>
                  <li>The organizers reserve the right of admission and are not responsible for lost belongings.</li>
                  <li>Any misconduct or violation of rules may result in immediate eviction without refund.</li>
                </ul>
              </div>
              <label className={`flex items-start gap-3 rounded-xl border p-3 text-xs ${
                readTerms
                  ? 'cursor-pointer border-slate-800 bg-slate-950/60 text-slate-300'
                  : 'cursor-not-allowed border-slate-800/60 bg-slate-950/30 text-slate-500'
              }`}>
                <input
                  type="checkbox"
                  checked={agreeTerms}
                  disabled={!readTerms}
                  onChange={(e) => setAgreeTerms(e.target.checked)}
                  className="mt-0.5 rounded border-slate-700 text-indigo-600 focus:ring-indigo-500"
                />
                <span>
                  {readTerms
                    ? 'I have read and agree to the Terms & Conditions.'
                    : 'Scroll through all Terms & Conditions above before agreeing.'}
                </span>
              </label>
            </section>

            {/* Buttons */}
            <div className="pt-4 border-t border-slate-800 flex justify-between items-center">
              <button
                type="button"
                onClick={() => setStep(2)}
                disabled={isSubmitting}
                className="px-4 py-2.5 text-xs text-slate-400 hover:text-white inline-flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Back</span>
              </button>

              <button
                type="button"
                onClick={handleSubmitRegistration}
                disabled={isSubmitting || !readTerms || !agreeTerms}
                className="px-8 py-3.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold uppercase tracking-wider inline-flex items-center gap-2 cursor-pointer transition-all shadow-lg shadow-indigo-600/30"
              >
                {isSubmitting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Opening Secure Checkout...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4" />
                    <span>PAY &amp; ISSUE PASS</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
          </>
        )}
      </main>

      <Footer />
    </div>
  );
};
