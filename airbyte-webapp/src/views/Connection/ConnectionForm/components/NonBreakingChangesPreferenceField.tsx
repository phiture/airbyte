import classNames from "classnames";
import { FieldProps } from "formik";
import { useMemo } from "react";
import { useIntl } from "react-intl";

import { ControlLabels } from "components";
import { DropDown } from "components/ui/DropDown";

import { NonBreakingChangesPreference } from "core/request/AirbyteClient";
import { useConnectionFormService } from "hooks/services/ConnectionForm/ConnectionFormService";

import styles from "./NonBreakingChangesPreferenceField.module.scss";

const SUPPORTED_PREFERENCES = [NonBreakingChangesPreference.ignore, NonBreakingChangesPreference.disable];

export const NonBreakingChangesPreferenceField: React.FC<FieldProps<string>> = ({ field, form }) => {
  const { formatMessage } = useIntl();

  const preferenceOptions = useMemo(() => {
    return SUPPORTED_PREFERENCES.map((value) => ({
      value,
      label: formatMessage({ id: `connectionForm.nonBreakingChangesPreference.${value}` }),
      testId: `nonBreakingChangesPreference-${value}`,
    }));
  }, [formatMessage]);

  const { mode } = useConnectionFormService();

  return (
    <div className={styles.flexRow}>
      <div className={styles.leftFieldCol}>
        <ControlLabels
          nextLine
          label={formatMessage({
            id: "connectionForm.nonBreakingChangesPreference.label",
          })}
          message={formatMessage({
            id: "connectionForm.nonBreakingChangesPreference.message",
          })}
        />
      </div>
      <div className={classNames(styles.rightFieldCol, { [styles.disabled]: mode === "readonly" })}>
        <DropDown
          {...field}
          options={preferenceOptions}
          error={form.touched[field.name] && !!form.errors[field.name]}
          data-testid="nonBreakingChangesPreference"
          value={field.value}
          onChange={({ value }) => form.setFieldValue(field.name, value)}
        />
      </div>
    </div>
  );
};
