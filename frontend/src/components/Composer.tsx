import { useEffect, useRef, type FormEvent } from "react";

import type { ApiError } from "../types/api";
import { ArrowUpIcon, PlusIcon } from "./icons";
import styles from "./Composer.module.css";

const EXAMPLE_ADDRESS = "4600 Silver Hill Rd Washington DC 20233";

interface ComposerProps {
  address: string;
  docked: boolean;
  error: ApiError | null;
  isLoading: boolean;
  onAddressChange: (value: string) => void;
  onSubmit: (address: string) => void;
}

export default function Composer({
  address,
  docked,
  error,
  isLoading,
  onAddressChange,
  onSubmit,
}: ComposerProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!docked) {
      inputRef.current?.focus();
    }
  }, [docked]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isLoading) {
      onSubmit(address);
    }
  }

  return (
    <div className={`${styles.wrap} ${docked ? styles.docked : ""}`}>
      <form className={styles.bar} onSubmit={handleSubmit}>
        <button
          className={styles.ghost}
          onClick={() => onAddressChange(EXAMPLE_ADDRESS)}
          type="button"
          aria-label="Use example address"
        >
          <PlusIcon />
        </button>
        <label className={styles.srOnly} htmlFor="address-search">
          Address
        </label>
        <input
          id="address-search"
          ref={inputRef}
          className={styles.input}
          onChange={(event) => onAddressChange(event.target.value)}
            placeholder="An address, a block, a site"
          type="text"
          value={address}
          autoComplete="street-address"
        />
        <button
          className={styles.send}
          disabled={isLoading || address.trim().length === 0}
          type="submit"
          aria-label={isLoading ? "Working" : "Build brief"}
        >
          <ArrowUpIcon />
        </button>
      </form>
      {error ? (
        <p className={styles.error} role="alert">
          {error.message}
        </p>
      ) : isLoading ? (
        <p className={styles.status} aria-live="polite">
          Reading the environment
        </p>
      ) : null}
    </div>
  );
}
