import React from 'react';
import { ArrowRight, BookOpen, HeartHandshake, Lightbulb, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Footer } from '../../components/common/Footer';
import { Navbar } from '../../components/common/Navbar';

export const AboutPage: React.FC = () => (
  <div className="festival-public about-page min-h-screen flex flex-col bg-slate-950 text-slate-100">
    <Navbar />

    <main className="about-page__main flex-1">
      <section className="about-intro" aria-labelledby="about-title">
        <div className="about-intro__inner">
          <div className="about-intro__identity">
            <img
              src="/sims-logo.png"
              srcSet="/sims-logo.webp"
              alt="Soundarya Institute of Management and Science logo"
            />
            <span className="about-eyebrow">A place to learn, lead &amp; thrive</span>
          </div>
          <div className="about-intro__copy">
            <p className="about-eyebrow">ABOUT SIMS</p>
            <h1 id="about-title">Learning today.<br /><em>Leading tomorrow.</em></h1>
            <p>
              Soundarya Institute of Management and Science (SIMS) is a premier institution
              dedicated to academic excellence and holistic development. With a strong reputation
              for nurturing future leaders, SIMS offers high-quality programs across disciplines.
            </p>
            <p>
              A dynamic curriculum, experienced faculty and modern infrastructure help students
              build industry-relevant skills, think critically and grow with ethical values.
              Students from across India make up a vibrant community where academic distinction,
              sports and cultural activities empower everyone to pursue their aspirations and
              contribute to society.
            </p>
            <Link to="/events/dhandiya-night-2026" className="about-intro__link">
              Explore our campus celebration <ArrowRight aria-hidden="true" />
            </Link>
          </div>
        </div>
      </section>

      <section className="about-daksha" aria-labelledby="daksha-title">
        <div className="about-daksha__inner">
          <div className="about-daksha__heading">
            <div className="about-daksha__logo">
              <img
                src="/daksha-student-council-emblem.png"
                srcSet="/daksha-student-council-emblem.webp"
                alt="Daksha Student Council emblem"
              />
            </div>
            <p className="about-eyebrow">STUDENT LIFE AT SIMS</p>
            <h2 id="daksha-title">Meet <em>DAKSHA</em></h2>
            <p className="about-daksha__tagline">The Student Council of SIMS</p>
          </div>

          <div className="about-daksha__content">
            <p className="about-daksha__lead">
              DAKSHA makes student life more connected, creative and meaningful.
            </p>
            <p>
              The Student Council enhances student life by fostering holistic development, serving
              as a communication bridge between the administration and students, and organizing
              cultural, social and educational activities. It gives students opportunities to
              develop leadership skills, plan programs and volunteer in their community.
            </p>

            <div className="about-values" aria-label="What DAKSHA encourages">
              <article className="about-value">
                <span><Users aria-hidden="true" /></span>
                <h3>Student voice</h3>
                <p>A bridge for communication between students and the administration.</p>
              </article>
              <article className="about-value">
                <span><Lightbulb aria-hidden="true" /></span>
                <h3>Leadership</h3>
                <p>Hands-on experience in planning programs and taking initiative.</p>
              </article>
              <article className="about-value">
                <span><HeartHandshake aria-hidden="true" /></span>
                <h3>Community</h3>
                <p>Opportunities to volunteer and take part in campus life.</p>
              </article>
              <article className="about-value">
                <span><BookOpen aria-hidden="true" /></span>
                <h3>Holistic growth</h3>
                <p>Cultural, social and educational activities beyond the classroom.</p>
              </article>
            </div>

            <div className="about-council">
              <div>
                <p className="about-eyebrow">HOW THE COUNCIL IS FORMED</p>
                <h3>A council shaped by student voices</h3>
              </div>
              <p>
                The Core Council includes a College President selected from the final year; two
                College Vice-Presidents, one male and one female, selected from the second-year
                batches; a Secretary, Joint Secretary, Cultural Secretary and Sports Secretary;
                and two Class Representatives from all streams. The larger Student Council brings
                together the Core Council, selected class representatives, and representatives
                from the college’s clubs and associations.
              </p>
            </div>

            <div className="about-coordinator">
              <span className="about-coordinator__mark" aria-hidden="true">✦</span>
              <p>
                <strong>Guided by faculty.</strong> A senior faculty member coordinates the
                Student Council and advises its student members.
              </p>
            </div>
          </div>
        </div>
      </section>
    </main>

    <Footer />
  </div>
);
