--
-- PostgreSQL database dump
--

-- Dumped from database version 16.6 (Ubuntu 16.6-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.6 (Ubuntu 16.6-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: testuser
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO testuser;

--
-- Name: credit_transactions; Type: TABLE; Schema: public; Owner: testuser
--

CREATE TABLE public.credit_transactions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    amount numeric(10,2) NOT NULL,
    transaction_type character varying(20) NOT NULL,
    reference_id character varying(100),
    description text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    user_credit_id integer NOT NULL
);


ALTER TABLE public.credit_transactions OWNER TO testuser;

--
-- Name: credit_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: testuser
--

CREATE SEQUENCE public.credit_transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.credit_transactions_id_seq OWNER TO testuser;

--
-- Name: credit_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: testuser
--

ALTER SEQUENCE public.credit_transactions_id_seq OWNED BY public.credit_transactions.id;


--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: testuser
--

CREATE TABLE public.password_reset_tokens (
    token character varying(255) NOT NULL,
    user_id integer NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    used boolean NOT NULL
);


ALTER TABLE public.password_reset_tokens OWNER TO testuser;

--
-- Name: personal_information; Type: TABLE; Schema: public; Owner: testuser
--

CREATE TABLE public.personal_information (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(100) NOT NULL,
    surname character varying(100) NOT NULL,
    date_of_birth character varying(10) NOT NULL,
    country character varying(100) NOT NULL,
    city character varying(100) NOT NULL,
    zip_code character varying(20),
    address character varying(255) NOT NULL,
    phone_prefix character varying(5) NOT NULL,
    phone character varying(20) NOT NULL,
    github character varying(255),
    linkedin character varying(255),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.personal_information OWNER TO testuser;

--
-- Name: personal_information_id_seq; Type: SEQUENCE; Schema: public; Owner: testuser
--

CREATE SEQUENCE public.personal_information_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.personal_information_id_seq OWNER TO testuser;

--
-- Name: personal_information_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: testuser
--

ALTER SEQUENCE public.personal_information_id_seq OWNED BY public.personal_information.id;


--
-- Name: user_credits; Type: TABLE; Schema: public; Owner: testuser
--

CREATE TABLE public.user_credits (
    id integer NOT NULL,
    user_id integer NOT NULL,
    balance numeric(10,2) DEFAULT '0'::numeric NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.user_credits OWNER TO testuser;

--
-- Name: user_credits_id_seq; Type: SEQUENCE; Schema: public; Owner: testuser
--

CREATE SEQUENCE public.user_credits_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_credits_id_seq OWNER TO testuser;

--
-- Name: user_credits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: testuser
--

ALTER SEQUENCE public.user_credits_id_seq OWNED BY public.user_credits.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: testuser
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(50) NOT NULL,
    email character varying(100) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    is_admin boolean NOT NULL
);


ALTER TABLE public.users OWNER TO testuser;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: testuser
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO testuser;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: testuser
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: credit_transactions id; Type: DEFAULT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.credit_transactions ALTER COLUMN id SET DEFAULT nextval('public.credit_transactions_id_seq'::regclass);


--
-- Name: personal_information id; Type: DEFAULT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.personal_information ALTER COLUMN id SET DEFAULT nextval('public.personal_information_id_seq'::regclass);


--
-- Name: user_credits id; Type: DEFAULT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.user_credits ALTER COLUMN id SET DEFAULT nextval('public.user_credits_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: testuser
--

COPY public.alembic_version (version_num) FROM stdin;
b3935b697a72
\.


--
-- Data for Name: credit_transactions; Type: TABLE DATA; Schema: public; Owner: testuser
--

COPY public.credit_transactions (id, user_id, amount, transaction_type, reference_id, description, created_at, user_credit_id) FROM stdin;
1	11	50.00	credit_added	test123	Test credit addition	2025-02-06 20:11:08.046504+01	1
\.


--
-- Data for Name: password_reset_tokens; Type: TABLE DATA; Schema: public; Owner: testuser
--

COPY public.password_reset_tokens (token, user_id, expires_at, used) FROM stdin;
\.


--
-- Data for Name: personal_information; Type: TABLE DATA; Schema: public; Owner: testuser
--

COPY public.personal_information (id, user_id, name, surname, date_of_birth, country, city, zip_code, address, phone_prefix, phone, github, linkedin, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: user_credits; Type: TABLE DATA; Schema: public; Owner: testuser
--

COPY public.user_credits (id, user_id, balance, created_at, updated_at) FROM stdin;
1	11	50.00	2025-02-06 20:07:00.097723	2025-02-06 20:11:08.039909
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: testuser
--

COPY public.users (id, username, email, hashed_password, is_admin) FROM stdin;
1	testuser_bff860a5	testuser_bff860a5@example.com	$2b$12$p3xHNnI9CkdI7ilNhQ8tO.xaIIzn7L8FfiarAUcW23ItFmpyQWeHK	f
2	testuser_88cb50d7	testuser_88cb50d7@example.com	$2b$12$QEgGOczAbd7bTuxS7KeUse4k9s35.rbNDDgxiZA6rjjbd.N/wMDsO	f
3	testuser_0cb69abf	testuser_0cb69abf@example.com	$2b$12$WDiRsvnM.wG.VQg3JPiaqOGVDMHrq9b2Ob.fDTvgbWf57VThLutU6	f
5	testuser_ab5e9483	testuser_ab5e9483@example.com	$2b$12$dTUhueTn.noOthmRRwihI.oaMXYjwRh1Szswpli8gfSCuM2xHzOYG	f
6	testuser_b40c2709	testuser_b40c2709@example.com	$2b$12$rfGCugWuFfLNQuKkL7eF2uZvh8i/BrwT3F/Xq4acCDXH2WEsrbRq6	f
7	divadd	alvarezdavid@gmail.com	$2b$12$d54dVyg0H2XBMjlIQNaVNugimYmdLcpNFJRWGxmis5jsleZTVvHdq	f
8	Hussein17	h.hijazi711@gmail.com	$2b$12$5AFSeX.S.oja6S4AocjE8.E9E9RQWRwSS1sKehVWlWzBAcbA06vCe	f
4	johndoe	ciao@ciao.it	$2b$12$cuAJDTedilRTJc0vwPVScOA2uMDOYL3lkLa0/VXfok3Hp5qYrt1N.	f
10	testuser_75d18628	testuser_75d18628@example.com	$2b$12$7N1RgdWL7OsxN7IU/RCSaeqyCIBP7G5BjpuFdISQOW/TkRQ1vFvGy	f
11	testuser123	test@example.com	$2b$12$azOnHiRevBVMpGXs1K77NezZy/fOX.PL8jA2kr8vwAVN9Qqjx0KQq	f
16	saaa	testa@example.com	$2b$12$xz2aG05H8qNgYYyy9wG8EuaQtqVtiAZEWvB..eKp8r/L8OcoeiMRW	f
18	testuser456	testuser456@example.com	$2b$12$8oNzVZASuFXJhSsOYSy1w.8rC4UWhQgz.J95pUsh88MNyVQUsO9r.	f
19	testuser789	newemail789@example.com	$2b$12$RPXj.nCUv86YHiix89xkrOiWLQrzPb6XpxSRJB8XfPZzZgA/Hq17.	f
21	lorenzo	newemail@example.com	$2b$12$cWA/QHDq7zkp1vaiA4mU5esn9C1RMM0sfRu8x8lBsFYBf1YD9IINW	f
24	testuser2	test2@example.com	$2b$12$7q2W0V4DJR5n4tyPDYMDBexeJHZ0Dgic2PKTslQAK2BWONeQwAcIC	f
22	mcnic	vasya@admin.ru	$2b$12$.JGnUZmw6q1vDRA0jHbUle0iUW2r1d5heA7YDKm4MRNlYhQkK6zrm	f
\.


--
-- Name: credit_transactions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: testuser
--

SELECT pg_catalog.setval('public.credit_transactions_id_seq', 4, true);


--
-- Name: personal_information_id_seq; Type: SEQUENCE SET; Schema: public; Owner: testuser
--

SELECT pg_catalog.setval('public.personal_information_id_seq', 1, true);


--
-- Name: user_credits_id_seq; Type: SEQUENCE SET; Schema: public; Owner: testuser
--

SELECT pg_catalog.setval('public.user_credits_id_seq', 2, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: testuser
--

SELECT pg_catalog.setval('public.users_id_seq', 24, true);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: credit_transactions credit_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.credit_transactions
    ADD CONSTRAINT credit_transactions_pkey PRIMARY KEY (id);


--
-- Name: password_reset_tokens password_reset_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (token);


--
-- Name: personal_information personal_information_pkey; Type: CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.personal_information
    ADD CONSTRAINT personal_information_pkey PRIMARY KEY (id);


--
-- Name: personal_information personal_information_user_id_key; Type: CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.personal_information
    ADD CONSTRAINT personal_information_user_id_key UNIQUE (user_id);


--
-- Name: user_credits user_credits_pkey; Type: CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.user_credits
    ADD CONSTRAINT user_credits_pkey PRIMARY KEY (id);


--
-- Name: user_credits user_credits_user_id_key; Type: CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.user_credits
    ADD CONSTRAINT user_credits_user_id_key UNIQUE (user_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_credit_transactions_id; Type: INDEX; Schema: public; Owner: testuser
--

CREATE INDEX ix_credit_transactions_id ON public.credit_transactions USING btree (id);


--
-- Name: ix_personal_information_id; Type: INDEX; Schema: public; Owner: testuser
--

CREATE INDEX ix_personal_information_id ON public.personal_information USING btree (id);


--
-- Name: ix_personal_information_user_id; Type: INDEX; Schema: public; Owner: testuser
--

CREATE INDEX ix_personal_information_user_id ON public.personal_information USING btree (user_id);


--
-- Name: ix_user_credits_id; Type: INDEX; Schema: public; Owner: testuser
--

CREATE INDEX ix_user_credits_id ON public.user_credits USING btree (id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: testuser
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_id; Type: INDEX; Schema: public; Owner: testuser
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: testuser
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: credit_transactions credit_transactions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.credit_transactions
    ADD CONSTRAINT credit_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: credit_transactions fk_credit_transactions_user_credit; Type: FK CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.credit_transactions
    ADD CONSTRAINT fk_credit_transactions_user_credit FOREIGN KEY (user_credit_id) REFERENCES public.user_credits(id);


--
-- Name: password_reset_tokens password_reset_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: personal_information personal_information_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.personal_information
    ADD CONSTRAINT personal_information_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_credits user_credits_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: testuser
--

ALTER TABLE ONLY public.user_credits
    ADD CONSTRAINT user_credits_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

